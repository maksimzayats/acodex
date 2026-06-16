from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from typing_extensions import override

from acodex import (
    ALL_CODEX_APP_THREAD_TOOL_NAMES,
    CdpTarget,
    CodexAppCdpClient,
    CodexAppCdpSettings,
)
from acodex.asyncio.cdp.runtime import CdpRuntimeEvaluator
from acodex.asyncio.cdp.types import JsonObject, JsonValue


@dataclass(slots=True)
class FakeRuntime:
    responses: list[JsonValue]
    expressions: list[str] = field(default_factory=list)
    closed: bool = False

    async def evaluate(self, expression: str) -> JsonValue:
        self.expressions.append(expression)
        return self.responses.pop(0)

    async def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class FakeWebSocket:
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


def client_with_runtime(runtime: FakeRuntime) -> CodexAppCdpClient:
    async def target_fetcher(settings: CodexAppCdpSettings) -> tuple[CdpTarget, ...]:
        await asyncio.sleep(0)
        assert settings.endpoint == "http://cdp"
        assert settings.http_timeout == pytest.approx(10.0)
        return (
            CdpTarget(
                id="target",
                kind="page",
                url="app://-/index.html",
                websocket_debugger_url="ws://target",
            ),
        )

    async def runtime_connector(
        websocket_url: str,
        *,
        runtime_timeout: float,
    ) -> CdpRuntimeEvaluator:
        await asyncio.sleep(0)
        assert websocket_url == "ws://target"
        assert runtime_timeout == pytest.approx(30.0)
        return runtime

    return CodexAppCdpClient(
        "http://cdp",
        target_fetcher=target_fetcher,
        runtime_connector=runtime_connector,
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
