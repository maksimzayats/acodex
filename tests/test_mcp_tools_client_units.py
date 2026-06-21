from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Self, cast

import pytest

from acodex.core.mcp_tools import MCPToolClientError, MCPToolJSONRPCError, MCPToolsClient


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def test_mcp_tools_client_lists_and_calls_tools() -> None:
    requests: list[dict[str, Any]] = []
    responses = [
        {"jsonrpc": "2.0", "id": "1", "result": {"tools": [{"name": "codex_app.echo"}]}},
        {
            "jsonrpc": "2.0",
            "id": "2",
            "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
        },
    ]

    def opener(request: urllib.request.Request, *, timeout: float) -> FakeResponse:
        assert timeout == pytest.approx(12.0)
        requests.append(json.loads(cast("bytes", request.data).decode("utf-8")))
        return FakeResponse(responses.pop(0))

    client = MCPToolsClient(mcp_url="http://127.0.0.1:45218/mcp", timeout=12.0, _opener=opener)

    assert client.list_tools() == [{"name": "codex_app.echo"}]
    assert client.call_tool("codex_app.echo", {"value": 1}) == {
        "content": [{"type": "text", "text": "ok"}],
        "isError": False,
    }
    assert requests == [
        {"jsonrpc": "2.0", "id": "acodex-tools-1", "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": "acodex-tools-2",
            "method": "tools/call",
            "params": {"name": "codex_app.echo", "arguments": {"value": 1}},
        },
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{bad", "invalid JSON"),
        ([], "JSON object"),
        ({"jsonrpc": "2.0", "id": "1"}, "result must be an object"),
        ({"jsonrpc": "2.0", "id": "1", "result": {"tools": "bad"}}, "result.tools must be"),
        (
            {"jsonrpc": "2.0", "id": "1", "result": {"tools": ["bad"]}},
            "result.tools must contain objects",
        ),
        (
            {"jsonrpc": "2.0", "id": "1", "error": "bad"},
            "error must be an object",
        ),
        (
            {"jsonrpc": "2.0", "id": "1", "error": {"code": "bad", "message": 1}},
            "error must include code and message",
        ),
    ],
)
def test_mcp_tools_client_rejects_invalid_responses(payload: Any, message: str) -> None:
    client = MCPToolsClient(
        mcp_url="http://127.0.0.1:45218/mcp",
        _opener=lambda *_args, **_kwargs: FakeResponse(payload),
    )

    with pytest.raises(MCPToolClientError, match=message):
        client.list_tools()


def test_mcp_tools_client_surfaces_jsonrpc_errors() -> None:
    client = MCPToolsClient(
        mcp_url="http://127.0.0.1:45218/mcp",
        _opener=lambda *_args, **_kwargs: FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "error": {"code": -32602, "message": "bad params", "data": {"name": "echo"}},
            },
        ),
    )

    with pytest.raises(MCPToolJSONRPCError) as exc_info:
        client.list_tools()

    assert exc_info.value.code == -32602
    assert exc_info.value.data == {"name": "echo"}
    assert str(exc_info.value) == "bad params"


def test_mcp_tools_client_wraps_network_errors() -> None:
    def opener(*_args: object, **_kwargs: object) -> FakeResponse:
        raise urllib.error.URLError("offline")

    client = MCPToolsClient(mcp_url="http://127.0.0.1:45218/mcp", _opener=opener)

    with pytest.raises(MCPToolClientError, match="Could not reach MCP server"):
        client.list_tools()
