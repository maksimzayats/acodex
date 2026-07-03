from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest
from mcp import ErrorData
from mcp.shared.exceptions import McpError
from mcp.types import CONNECTION_CLOSED, CallToolResult, ListToolsResult, TextContent, Tool

from acodex.sdk import (
    AcodexConnectionError,
    AcodexResultError,
    AcodexToolError,
    AsyncAcodexClient,
    ToolResult,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeSession:
    def __init__(
        self,
        *,
        call_result: CallToolResult | None = None,
        call_error: BaseException | None = None,
        list_error: BaseException | None = None,
        tool_pages: list[ListToolsResult] | None = None,
    ) -> None:
        self.call_result = call_result
        self.call_error = call_error
        self.list_error = list_error
        self.tool_pages = tool_pages or []
        self.calls: list[tuple[str, dict[str, Any] | None, dict[str, Any]]] = []
        self.cursors: list[str | None] = []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> CallToolResult:
        self.calls.append((name, arguments, kwargs))
        if self.call_error is not None:
            raise self.call_error
        assert self.call_result is not None
        return self.call_result

    async def list_tools(
        self,
        cursor: str | None = None,
        *,
        params: Any = None,
    ) -> ListToolsResult:
        if params is not None:
            cursor = params.cursor
        self.cursors.append(cursor)
        if self.list_error is not None:
            raise self.list_error
        return self.tool_pages.pop(0)


class FakeExitStack:
    def __init__(self, *, close_error: BaseException | None = None) -> None:
        self.closed = False
        self.close_error = close_error

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def test_tool_result_text_and_json_conversion() -> None:
    result = ToolResult(
        content_items=[
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ],
        is_error=False,
    )

    assert result.text() == "hello\nworld"

    assert ToolResult(
        content_items=[{"type": "text", "text": '{"ok": true}'}],
        is_error=False,
    ).json_object() == {"ok": True}
    assert ToolResult(
        content_items=[],
        is_error=False,
        structured_content={"ok": True},
    ).json_object() == {"ok": True}


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            ToolResult(content_items=[], is_error=False),
            "did not include text",
        ),
        (
            ToolResult(content_items=[{"type": "text", "text": "{bad"}], is_error=False),
            "not valid JSON",
        ),
        (
            ToolResult(content_items=[{"type": "text", "text": "[1]"}], is_error=False),
            "must be an object",
        ),
    ],
)
def test_tool_result_reports_invalid_requested_shapes(
    result: ToolResult,
    message: str,
) -> None:
    with pytest.raises(AcodexResultError, match=message):
        result.json_object()


def test_tool_result_adapts_official_mcp_result() -> None:
    mcp_result = CallToolResult(
        content=[TextContent(type="text", text="ok")],
        structuredContent={"ok": True},
        isError=False,
        _meta={"requestId": "request-1"},
    )

    result = ToolResult.from_mcp(mcp_result)

    assert result.content_items == [{"type": "text", "text": "ok"}]
    assert result.structured_content == {"ok": True}
    assert result.meta == {"requestId": "request-1"}
    assert not result.is_error


def test_sdk_lists_tools_with_pagination() -> None:
    fake_session = FakeSession(
        tool_pages=[
            ListToolsResult(
                tools=[Tool(name="codex_app.one", inputSchema={"type": "object"})],
                nextCursor="cursor-2",
            ),
            ListToolsResult(
                tools=[
                    Tool(
                        name="codex_app.two",
                        title="Second tool",
                        inputSchema={"type": "object"},
                        outputSchema={"type": "object"},
                        _meta={"kind": "demo"},
                    ),
                ],
            ),
        ],
    )
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    assert run(client.list_tools()) == [
        {"name": "codex_app.one", "inputSchema": {"type": "object"}},
        {
            "name": "codex_app.two",
            "title": "Second tool",
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object"},
            "_meta": {"kind": "demo"},
        },
    ]
    assert fake_session.cursors == [None, "cursor-2"]


def test_sdk_calls_tools_and_converts_json() -> None:
    fake_session = FakeSession(
        call_result=CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"ok": True}))],
        ),
    )
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    assert run(client.call_json("codex_app.echo", {"value": 1})) == {"ok": True}
    assert fake_session.calls == [
        (
            "codex_app.echo",
            {"value": 1},
            {"read_timeout_seconds": timedelta(seconds=30.0)},
        ),
    ]


def test_sdk_calls_tools_and_returns_text() -> None:
    fake_session = FakeSession(
        call_result=CallToolResult(content=[TextContent(type="text", text="ok")]),
    )
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    assert run(client.call_text("codex_app.echo")) == "ok"
    assert fake_session.calls == [
        (
            "codex_app.echo",
            {},
            {"read_timeout_seconds": timedelta(seconds=30.0)},
        ),
    ]


def test_sdk_raises_for_tool_result_errors() -> None:
    fake_session = FakeSession(
        call_result=CallToolResult(
            content=[TextContent(type="text", text="tool failed")],
            isError=True,
        ),
    )
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    with pytest.raises(AcodexToolError, match="tool failed") as exc_info:
        run(client.call_tool("codex_app.fail"))

    assert exc_info.value.result is not None
    assert exc_info.value.result.text() == "tool failed"


def test_sdk_raises_generic_message_for_non_text_tool_errors() -> None:
    fake_session = FakeSession(call_result=CallToolResult(content=[], isError=True))
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    with pytest.raises(AcodexToolError, match="MCP tool returned an error"):
        run(client.call_tool("codex_app.fail"))


def test_sdk_maps_mcp_protocol_errors() -> None:
    fake_session = FakeSession(
        call_error=McpError(
            ErrorData(code=-32602, message="bad params", data={"name": "codex_app.fail"}),
        ),
    )
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    with pytest.raises(AcodexToolError, match="bad params") as exc_info:
        run(client.call_tool("codex_app.fail"))

    assert exc_info.value.code == -32602
    assert exc_info.value.data == {"name": "codex_app.fail"}


@pytest.mark.parametrize(
    "error_code",
    [CONNECTION_CLOSED, httpx.codes.REQUEST_TIMEOUT],
)
def test_sdk_maps_mcp_connection_codes(error_code: int) -> None:
    fake_session = FakeSession(
        call_error=McpError(ErrorData(code=error_code, message="connection failed")),
    )
    client = AsyncAcodexClient(mcp_url="http://127.0.0.1:1/mcp")
    client._session = cast("Any", fake_session)

    with pytest.raises(AcodexConnectionError, match="Could not call MCP tool"):
        run(client.call_tool("codex_app.echo"))


def test_sdk_maps_call_transport_errors() -> None:
    fake_session = FakeSession(call_error=httpx.ConnectError("offline"))
    client = AsyncAcodexClient(mcp_url="http://127.0.0.1:1/mcp")
    client._session = cast("Any", fake_session)

    with pytest.raises(AcodexConnectionError, match="Could not call MCP tool"):
        run(client.call_tool("codex_app.echo"))


def test_sdk_maps_list_tools_mcp_errors() -> None:
    fake_session = FakeSession(
        list_error=McpError(ErrorData(code=-32603, message="server failed")),
    )
    client = AsyncAcodexClient()
    client._session = cast("Any", fake_session)

    with pytest.raises(AcodexToolError, match="server failed") as exc_info:
        run(client.list_tools())

    assert exc_info.value.code == -32603


def test_sdk_requires_connection_before_calls() -> None:
    with pytest.raises(AcodexConnectionError, match="not connected"):
        run(AsyncAcodexClient().list_tools())

    with pytest.raises(AcodexConnectionError, match="not connected") as exc_info:
        run(AsyncAcodexClient().call_tool("codex_app.echo"))

    assert "Could not call MCP tool" not in str(exc_info.value)


def test_sdk_connect_and_close_are_idempotent() -> None:
    exit_stack = FakeExitStack()
    client = AsyncAcodexClient()
    client._session = cast("Any", object())
    client._exit_stack = cast("Any", exit_stack)

    run(client.connect())
    run(client.close())
    run(client.close())

    assert exit_stack.closed
    assert client._session is None
    assert client._exit_stack is None


def test_sdk_close_clears_state_when_cleanup_fails() -> None:
    exit_stack = FakeExitStack(close_error=RuntimeError("cleanup failed"))
    client = AsyncAcodexClient()
    client._session = cast("Any", object())
    client._exit_stack = cast("Any", exit_stack)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        run(client.close())

    assert exit_stack.closed
    assert client._session is None
    assert client._exit_stack is None


def test_sdk_connect_serializes_concurrent_calls(monkeypatch: Any) -> None:
    opened_sessions = 0

    async def open_session(
        self: AsyncAcodexClient,
        _exit_stack: Any,
    ) -> Any:
        nonlocal opened_sessions
        await asyncio.sleep(0)
        opened_sessions += 1
        return object()

    async def scenario() -> None:
        client = AsyncAcodexClient()
        await asyncio.gather(client.connect(), client.connect())

    monkeypatch.setattr(AsyncAcodexClient, "_open_session", open_session)

    run(scenario())

    assert opened_sessions == 1


def test_sdk_maps_connection_failures(monkeypatch: Any) -> None:
    async def fail_open_session(
        self: AsyncAcodexClient,
        _exit_stack: Any,
    ) -> None:
        await asyncio.sleep(0)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(AsyncAcodexClient, "_open_session", fail_open_session)

    with pytest.raises(AcodexConnectionError, match="Could not connect"):
        run(AsyncAcodexClient().connect())


def test_sdk_cleans_partial_session_after_connect_cancellation(monkeypatch: Any) -> None:
    async def cancel_open_session(
        self: AsyncAcodexClient,
        exit_stack: Any,
    ) -> Any:
        await asyncio.sleep(0)
        self._session = cast("Any", object())
        self._exit_stack = cast("Any", exit_stack)
        raise asyncio.CancelledError

    client = AsyncAcodexClient()
    monkeypatch.setattr(AsyncAcodexClient, "_open_session", cancel_open_session)

    with pytest.raises(asyncio.CancelledError):
        run(client.connect())

    assert client._session is None
    assert client._exit_stack is None
