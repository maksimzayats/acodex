from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any, cast

import pytest
import uvicorn
from diwire import Container, resolver_context
from fastapi import FastAPI

from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.http import app as app_module
from acodex.http.mcp.constants import MCP_PROTOCOL_VERSION
from acodex.http.mcp.handler import MCPRequestsHandler
from acodex.http.mcp.routes import mcp_router
from acodex.sdk import AsyncAcodexClient

LOCAL_HOST = "127.0.0.1"
SERVER_STARTUP_TIMEOUT = 10.0
SERVER_PROBE_TIMEOUT = 0.5


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "codex_app.echo",
                "description": "Echo arguments as JSON text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                },
            },
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> dict[str, Any]:
        tool_arguments = arguments or {}
        self.calls.append((name, tool_arguments))
        return {
            "contentItems": [
                {
                    "type": "inputText",
                    "text": json.dumps(
                        {"name": name, "arguments": tool_arguments},
                        ensure_ascii=False,
                    ),
                },
            ],
        }


@pytest.fixture()
def mcp_endpoint() -> Iterator[str]:
    fake_bridge = FakeBridge()
    original_container = app_module.container
    resolver_context.set_fallback_container(_fake_container(fake_bridge))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((LOCAL_HOST, 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(
        _fake_app(),
        host=LOCAL_HOST,
        port=port,
        lifespan="off",
        log_level="warning",
        ws="none",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        daemon=True,
        name="acodex-sdk-mcp-test-server",
    )
    thread.start()

    url = f"http://{LOCAL_HOST}:{port}/mcp"
    try:
        _wait_for_mcp(url)
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        resolver_context.set_fallback_container(original_container)
        if thread.is_alive():
            pytest.fail("Uvicorn SDK MCP test server did not stop")


def test_sdk_uses_official_mcp_client_against_acodex_mcp_route(
    mcp_endpoint: str,
) -> None:
    async def scenario() -> None:
        async with AsyncAcodexClient(mcp_url=mcp_endpoint) as client:
            tools = await client.list_tools()
            payload = await client.call_json("codex_app.echo", {"value": 42})

        assert tools == [
            {
                "name": "codex_app.echo",
                "description": "Echo arguments as JSON text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                },
            },
        ]
        assert payload == {
            "name": "codex_app.echo",
            "arguments": {"value": 42},
        }

    run(scenario())


def _fake_container(fake_bridge: FakeBridge) -> Container:
    container = Container()
    container.add_instance(cast("CodexAppBridge", fake_bridge), provides=CodexAppBridge)
    container.add(MCPRequestsHandler)
    return container


def _fake_app() -> FastAPI:
    app = FastAPI()
    app.include_router(mcp_router)
    return app


def _wait_for_mcp(url: str) -> None:
    deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            _post_initialize(url)
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.05)
        else:
            return
    pytest.fail(f"MCP test server did not start: {last_error!r}")


def _post_initialize(url: str) -> None:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "sdk-test-initialize",
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "acodex-sdk-test", "version": "0"},
                },
            },
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": f"http://{LOCAL_HOST}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=SERVER_PROBE_TIMEOUT) as response:  # noqa: S310
        response.read()
