from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, TypeAlias, cast

import websockets
from diwire import Injected

from acodex.core.codex_app.cdp.errors import CodexCDPError
from acodex.core.codex_app.cdp.settings import CodexCDPSettings
from acodex.core.codex_app.cdp.targets import CodexTargetDiscovery

PendingResponses: TypeAlias = dict[int, asyncio.Future[dict[str, Any]]]


def pending_responses() -> PendingResponses:
    return {}


@dataclass(kw_only=True, slots=True)
class CodexCDPClient:
    """Command client for the Codex app Chrome DevTools Protocol endpoint."""

    _settings: Injected[CodexCDPSettings]
    _next_id: int = field(default=0, init=False)
    _pending: PendingResponses = field(default_factory=pending_responses, init=False)
    _recv_task: asyncio.Task[None] | None = field(default=None, init=False)
    _ws: Any | None = field(default=None, init=False)
    _connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def close(self) -> None:
        """Close the CDP websocket and fail pending commands."""
        websocket = self._ws
        if self._recv_task is not None:
            self._recv_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None

        if websocket is not None:
            await websocket.close()
            self._ws = None

        self._fail_pending(CodexCDPError("CDP connection closed"))

    async def command(
        self,
        method: str,
        command_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a Chrome DevTools Protocol command against the Codex renderer."""
        await self._ensure_connected()
        if self._ws is None:
            raise CodexCDPError("CDP websocket is not connected")

        message_id, response_future = self._create_pending_response()
        command_payload: dict[str, Any] = {"id": message_id, "method": method}
        if command_params is not None:
            command_payload["params"] = command_params

        try:
            await self._ws.send(json.dumps(command_payload))
            response_payload = await asyncio.wait_for(
                response_future,
                timeout=self._settings.request_timeout,
            )
        except Exception:
            self._pending.pop(message_id, None)
            raise

        return self._response_result(method, response_payload)

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        """Evaluate JavaScript in the Codex renderer."""
        command_result = await self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        return EvaluationResult(command_result).value()

    async def resource_tree(self) -> dict[str, Any]:
        """Return the renderer resource tree."""
        return await self.command("Page.getResourceTree")

    async def resource_content(self, frame_id: str, url: str) -> str:
        """Read a text resource loaded by the renderer."""
        command_result = await self.command(
            "Page.getResourceContent",
            {"frameId": frame_id, "url": url},
        )
        if command_result.get("base64Encoded"):
            raise CodexCDPError(f"resource is base64 encoded and cannot be scanned: {url}")
        resource_content = command_result.get("content", "")
        return resource_content if isinstance(resource_content, str) else ""

    async def _ensure_connected(self) -> None:
        async with self._connect_lock:
            if self._ws is not None:
                return

            target_payload = await asyncio.to_thread(self._find_codex_target)
            websocket_url = target_payload.get("webSocketDebuggerUrl")
            if not isinstance(websocket_url, str) or not websocket_url:
                raise CodexCDPError("Codex CDP target did not include a websocket URL")

            self._ws = await websockets.connect(
                websocket_url,
                max_size=None,
                open_timeout=self._settings.request_timeout,
            )
            self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self) -> None:
        if self._ws is None:
            return

        close_error: BaseException | None = None
        try:
            async for raw_message in self._ws:
                self._handle_recv_message(raw_message)
        except (websockets.ConnectionClosed, OSError) as exc:
            close_error = exc
        finally:
            self._ws = None
            self._fail_pending(close_error or CodexCDPError("CDP connection closed"))

    def _handle_recv_message(self, raw_message: str | bytes) -> None:
        try:
            message_payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return
        if not isinstance(message_payload, dict):
            return
        typed_message = cast("dict[str, Any]", message_payload)
        message_id = typed_message.get("id")
        if not isinstance(message_id, int):
            return
        response_future = self._pending.pop(message_id, None)
        if response_future is not None and not response_future.done():
            response_future.set_result(typed_message)

    def _fail_pending(self, exc: BaseException) -> None:
        for response_future in self._pending.values():
            if not response_future.done():
                response_future.set_exception(exc)
        self._pending.clear()

    def _find_codex_target(self) -> dict[str, Any]:
        return CodexTargetDiscovery(self._settings).find_target()

    def _create_pending_response(self) -> tuple[int, asyncio.Future[dict[str, Any]]]:
        self._next_id += 1
        message_id = self._next_id
        response_future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = response_future
        return message_id, response_future

    def _response_result(self, method: str, response_payload: dict[str, Any]) -> dict[str, Any]:
        response_error = response_payload.get("error")
        if response_error is not None:
            raise CodexCDPError("CDP {} failed: {}".format(method, response_error))
        command_result = response_payload.get("result", {})
        return cast("dict[str, Any]", command_result) if isinstance(command_result, dict) else {}


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Interpret a Runtime.evaluate response payload."""

    payload: dict[str, Any]

    def value(self) -> Any:
        """Return the renderer evaluation value or raise an evaluation error."""
        exception_payload = self.payload.get("exceptionDetails")
        if isinstance(exception_payload, dict):
            self._raise_exception(cast("dict[str, Any]", exception_payload))

        remote_object = self.payload.get("result", {})
        if not isinstance(remote_object, dict):
            return remote_object
        typed_remote_object = cast("dict[str, Any]", remote_object)
        if "value" in typed_remote_object:
            return typed_remote_object.get("value")
        if typed_remote_object.get("subtype") == "null":
            return None
        description = typed_remote_object.get("description")
        if description:
            return description
        return typed_remote_object

    def _raise_exception(self, exception_payload: dict[str, Any]) -> None:
        text_payload = exception_payload.get("text") or "renderer evaluation failed"
        exception_value = exception_payload.get("exception", {})
        details = (
            cast("dict[str, Any]", exception_value).get("description")
            if isinstance(exception_value, dict)
            else None
        )
        if details:
            raise CodexCDPError(f"{text_payload}: {details}")
        raise CodexCDPError(str(text_payload))
