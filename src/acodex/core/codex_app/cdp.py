from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, cast

import websockets
from diwire import Injected
from pydantic_settings import BaseSettings, SettingsConfigDict


class CodexCDPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACODEX_CODEX_APP_CDP_")

    host: str = "127.0.0.1"
    port: int = 5633
    request_timeout: float = 10.0

    @property
    def base_url(self) -> str:
        """Return the base URL for the Codex app CDP endpoint."""
        return f"http://{self.host}:{self.port}"


@dataclass(kw_only=True, slots=True)
class CodexCDPClient:
    _settings: Injected[CodexCDPSettings]
    _next_id: int = field(default=0, init=False)
    _pending: dict[int, asyncio.Future[dict[str, Any]]] = field(default_factory=dict, init=False)
    _recv_task: asyncio.Task[None] | None = field(default=None, init=False)
    _ws: Any | None = field(default=None, init=False)
    _connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def close(self) -> None:
        """Close the CDP websocket and fail pending commands."""
        ws = self._ws
        if self._recv_task is not None:
            self._recv_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None

        if ws is not None:
            await ws.close()
            self._ws = None

        self._fail_pending(CodexCDPError("CDP connection closed"))

    async def command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a Chrome DevTools Protocol command against the Codex renderer.

        Returns:
            The CDP command result object.

        Raises:
            CodexCDPError: If the command fails or the renderer is unavailable.

        """
        await self._ensure_connected()
        if self._ws is None:
            raise CodexCDPError("CDP websocket is not connected")

        self._next_id += 1
        message_id = self._next_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[message_id] = future

        payload: dict[str, Any] = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params

        try:
            await self._ws.send(json.dumps(payload))
            response = await asyncio.wait_for(future, timeout=self._settings.request_timeout)
        except Exception:
            self._pending.pop(message_id, None)
            raise

        if "error" in response:
            raise CodexCDPError(f"CDP {method} failed: {response['error']}")
        result = response.get("result", {})
        return result if isinstance(result, dict) else {}

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        """Evaluate JavaScript in the Codex renderer.

        Returns:
            The renderer evaluation value.

        Raises:
            CodexCDPError: If evaluation fails in the renderer.

        """
        result = await self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        exception = result.get("exceptionDetails")
        if isinstance(exception, dict):
            text = exception.get("text") or "renderer evaluation failed"
            exception_value = exception.get("exception", {})
            details = (
                exception_value.get("description") if isinstance(exception_value, dict) else None
            )
            raise CodexCDPError(f"{text}: {details}" if details else str(text))

        remote = result.get("result", {})
        if not isinstance(remote, dict):
            return remote
        if "value" in remote:
            return remote["value"]
        if remote.get("subtype") == "null":
            return None
        description = remote.get("description")
        if description:
            return description
        return remote

    async def resource_tree(self) -> dict[str, Any]:
        """Return the renderer resource tree.

        Returns:
            The CDP resource tree result.

        """
        return await self.command("Page.getResourceTree")

    async def resource_content(self, frame_id: str, url: str) -> str:
        """Read a text resource loaded by the renderer.

        Returns:
            The text content for the requested resource.

        Raises:
            CodexCDPError: If the resource is not readable text.

        """
        result = await self.command("Page.getResourceContent", {"frameId": frame_id, "url": url})
        if result.get("base64Encoded"):
            raise CodexCDPError(f"resource is base64 encoded and cannot be scanned: {url}")
        content = result.get("content", "")
        return content if isinstance(content, str) else ""

    async def _ensure_connected(self) -> None:
        async with self._connect_lock:
            if self._ws is not None:
                return

            target = await asyncio.to_thread(self._find_codex_target)
            websocket_url = target.get("webSocketDebuggerUrl")
            if not isinstance(websocket_url, str) or not websocket_url:
                raise CodexCDPError("Codex CDP target did not include a websocket URL")

            self._ws = await websockets.connect(
                websocket_url,
                open_timeout=self._settings.request_timeout,
            )
            self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self) -> None:
        if self._ws is None:
            return

        close_error: BaseException | None = None
        try:
            async for raw in self._ws:
                self._handle_recv_message(raw)
        except (websockets.ConnectionClosed, OSError) as exc:
            close_error = exc
        finally:
            self._ws = None
            self._fail_pending(close_error or CodexCDPError("CDP connection closed"))

    def _handle_recv_message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        message_id = message.get("id")
        if not isinstance(message_id, int):
            return
        future = self._pending.pop(message_id, None)
        if future is not None and not future.done():
            future.set_result(cast("dict[str, Any]", message))

    def _fail_pending(self, exc: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    def _find_codex_target(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(  # noqa: S310 - CDP base URL is explicit local configuration.
                f"{self._settings.base_url}/json/list",
                timeout=self._settings.request_timeout,
            ) as response:
                targets = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError) as exc:
            raise CodexCDPError(
                f"Could not reach Codex CDP at {self._settings.base_url}. "
                "Start Codex with --remote-debugging-port or set ACODEX_CODEX_APP_CDP_PORT.",
            ) from exc

        if not isinstance(targets, list) or not targets:
            raise CodexCDPError(f"No CDP targets found at {self._settings.base_url}")

        for target in targets:
            if not isinstance(target, dict):
                continue
            url = target.get("url", "")
            if target.get("type") == "page" and isinstance(url, str) and url.startswith("app://-"):
                return cast("dict[str, Any]", target)

        for target in targets:
            if isinstance(target, dict) and target.get("type") == "page":
                return cast("dict[str, Any]", target)

        raise CodexCDPError(f"No page target found at {self._settings.base_url}")


class CodexCDPError(RuntimeError):
    """Raised when the Codex renderer cannot be reached or evaluated."""
