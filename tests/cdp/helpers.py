from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from typing_extensions import override

from acodex.adapters.sdk.asyncio.client import AsyncCodexApp
from acodex.core.asyncio.cdp.backend import CodexAppCdpBackend
from acodex.core.asyncio.cdp.renderer import ALL_CODEX_APP_THREAD_TOOL_NAMES
from acodex.core.asyncio.cdp.runtime import CdpRuntime, CdpRuntimeConnector, CdpWebSocket
from acodex.core.asyncio.cdp.settings import CodexAppCdpSettings
from acodex.core.asyncio.cdp.targets import CdpTargetFetcher
from acodex.core.asyncio.cdp.types import CdpTarget, JsonObject, JsonValue


@dataclass(slots=True)
class FakeRuntime(CdpRuntime):
    responses: list[JsonValue]
    expressions: list[str] = field(default_factory=list)
    closed: bool = False

    async def evaluate(self, expression: str) -> JsonValue:
        self.expressions.append(expression)
        return self.responses.pop(0)

    async def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class FakeWebSocket(CdpWebSocket):
    incoming: list[str | bytes]
    sent: list[str] = field(default_factory=list)
    closed: bool = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        return self.incoming.pop(0)

    async def close(self) -> None:
        self.closed = True


class JsonServer:
    def __init__(self, *, status: int, body: JsonValue) -> None:
        self.paths: list[str] = []
        handler = self._handler(status=status, body=body, paths=self.paths)
        self._server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()

    @staticmethod
    def _handler(
        *,
        status: int,
        body: JsonValue,
        paths: list[str],
    ) -> type[BaseHTTPRequestHandler]:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                paths.append(self.path)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode("utf-8"))

            @override
            def log_message(self, format_: str, *args: Any) -> None:
                return

        return Handler


@dataclass(slots=True)
class FakeTargetFetcher(CdpTargetFetcher):
    targets: tuple[CdpTarget, ...] = (
        CdpTarget(
            id="target",
            kind="page",
            url="app://-/index.html",
            websocket_debugger_url="ws://target",
        ),
    )
    endpoints: list[str] = field(default_factory=list)
    http_timeouts: list[float] = field(default_factory=list)

    async def fetch(
        self,
        endpoint: str = "http://127.0.0.1:9222",
        *,
        http_timeout: float = 10.0,
    ) -> tuple[CdpTarget, ...]:
        await asyncio.sleep(0)
        self.endpoints.append(endpoint)
        self.http_timeouts.append(http_timeout)
        return self.targets


@dataclass(slots=True)
class FakeRuntimeConnector(CdpRuntimeConnector):
    runtime: CdpRuntime
    websocket_urls: list[str] = field(default_factory=list)
    runtime_timeouts: list[float] = field(default_factory=list)

    async def connect(
        self,
        websocket_url: str,
        *,
        runtime_timeout: float = 30.0,
    ) -> CdpRuntime:
        await asyncio.sleep(0)
        self.websocket_urls.append(websocket_url)
        self.runtime_timeouts.append(runtime_timeout)
        return self.runtime


def client_with_runtime(runtime: FakeRuntime) -> AsyncCodexApp:
    return AsyncCodexApp(backend=backend_with_runtime(runtime))


def backend_with_runtime(runtime: FakeRuntime) -> CodexAppCdpBackend:
    return CodexAppCdpBackend(
        settings=CodexAppCdpSettings(endpoint="http://cdp"),
        target_fetcher=FakeTargetFetcher(),
        runtime_connector=FakeRuntimeConnector(runtime),
    )


def default_targets() -> tuple[CdpTarget, ...]:
    return (
        CdpTarget(
            id="target",
            kind="page",
            url="app://-/index.html",
            websocket_debugger_url="ws://target",
        ),
    )


def discovery_result(tool_names: tuple[str, ...]) -> JsonObject:
    return {
        "toolNames": list(tool_names),
        "missingToolNames": [
            name for name in ALL_CODEX_APP_THREAD_TOOL_NAMES if name not in tool_names
        ],
        "toolExports": {name: chr(97 + index) for index, name in enumerate(tool_names)},
        "toolChunkUrls": ["app://-/assets/tools.js"],
        "rpcChunkUrls": ["app://-/assets/rpc.js"],
    }


def renderer_success(value: JsonValue) -> JsonObject:
    return {
        "contentItems": [{"type": "inputText", "text": json.dumps(value)}],
        "success": True,
    }
