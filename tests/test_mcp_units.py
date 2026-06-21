from __future__ import annotations

import asyncio
import json
from json import JSONDecodeError
from typing import Any, cast

from mcp import ErrorData, JSONRPCError, JSONRPCResponse
from mcp.types import JSONRPCNotification, JSONRPCRequest
from starlette.requests import Request

from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.core.codex_app.cdp import CodexCDPSettings
from acodex.http.mcp import routes
from acodex.http.mcp.constants import MCP_PROTOCOL_VERSION
from acodex.http.mcp.handler import MCPRequestsHandler
from acodex.http.mcp.result_adapter import MCPResultAdapter


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def response_payload(response: Any) -> Any:
    return json.loads(response.body.decode("utf-8"))


def unwrapped_route(route: Any) -> Any:
    return route.__wrapped__


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[dict[str, Any]]:
        assert isinstance(self.calls, list)
        return [{"name": "codex_app.echo"}]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if name == "value-error":
            raise ValueError("bad params")
        if name == "type-error":
            raise TypeError("wrong params")
        if name == "runtime-error":
            raise RuntimeError("boom")
        return {"contentItems": [{"type": "inputText", "text": f"{name}:{arguments}"}]}


class FakeRequest:
    def __init__(
        self,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        json_error: JSONDecodeError | None = None,
    ) -> None:
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error

    async def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeRoutesHandler:
    def __init__(self) -> None:
        self.handled = 0

    async def handle_mcp_jsonrpc_message(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
    ) -> JSONRPCResponse | JSONRPCError | None:
        self.handled += 1
        if isinstance(message, JSONRPCNotification):
            return None
        if message.method == "fail":
            return JSONRPCError(
                jsonrpc="2.0",
                id=message.id,
                error=ErrorData(code=-32603, message="failed"),
            )
        return JSONRPCResponse(jsonrpc="2.0", id=message.id, result={"method": message.method})


def test_routes_validate_and_dispatch_jsonrpc_messages() -> None:
    handler = FakeRoutesHandler()

    single = run(
        unwrapped_route(routes.handle_mcp)(
            FakeRequest({"jsonrpc": "2.0", "id": "1", "method": "ping"}),
            handler=handler,
        ),
    )
    assert response_payload(single) == {"jsonrpc": "2.0", "id": "1", "result": {"method": "ping"}}
    assert single.headers["mcp-protocol-version"] == MCP_PROTOCOL_VERSION

    batch = run(
        unwrapped_route(routes.handle_mcp)(
            FakeRequest(
                [
                    {"jsonrpc": "2.0", "id": 2, "method": "ping"},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 3, "method": "fail"},
                    "not an object",
                ],
            ),
            handler=handler,
        ),
    )
    assert response_payload(batch) == [
        {"jsonrpc": "2.0", "id": 2, "result": {"method": "ping"}},
        {"jsonrpc": "2.0", "id": 3, "error": {"code": -32603, "message": "failed"}},
        {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
    ]

    notification_only = run(
        unwrapped_route(routes.handle_mcp)(
            FakeRequest([{"jsonrpc": "2.0", "method": "notifications/initialized"}]),
            handler=handler,
        ),
    )
    assert notification_only.status_code == 202


def test_routes_reject_invalid_requests_and_origins() -> None:
    handler = FakeRoutesHandler()

    forbidden = run(
        unwrapped_route(routes.handle_mcp)(
            FakeRequest(headers={"Origin": "https://example.com"}),
            handler=handler,
        ),
    )
    assert forbidden.status_code == 403
    assert response_payload(forbidden) == {"error": "forbidden origin"}

    parse_error = run(
        unwrapped_route(routes.handle_mcp)(
            FakeRequest(json_error=JSONDecodeError("bad", "x", 0)),
            handler=handler,
        ),
    )
    assert response_payload(parse_error)["error"]["code"] == -32700

    empty_batch = run(routes._handle_batch([], cast("MCPRequestsHandler", handler)))
    assert response_payload(empty_batch) == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }

    invalid_id = routes._validate_message({"jsonrpc": "2.0", "id": True, "method": 1})
    assert invalid_id == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }
    invalid_single = run(
        routes._handle_single("not an object", cast("MCPRequestsHandler", handler)),
    )
    assert response_payload(invalid_single)["error"]["code"] == -32600
    single_notification = run(
        routes._handle_single(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            cast("MCPRequestsHandler", handler),
        ),
    )
    assert single_notification.status_code == 202
    assert routes._response_id("id") == "id"
    assert routes._response_id(1) == 1
    assert routes._response_id([]) is None
    assert routes._is_allowed_origin(
        cast("Request", FakeRequest(headers={"Origin": "http://localhost"})),
    )
    assert routes._is_allowed_origin(
        cast("Request", FakeRequest(headers={"Origin": "http://[::1]"})),
    )
    assert not routes._is_allowed_origin(
        cast("Request", FakeRequest(headers={"Origin": "http://["})),
    )


def test_healthz_returns_cdp_endpoint() -> None:
    response = run(unwrapped_route(routes.healthz)(cdp_settings=CodexCDPSettings(port=9999)))
    assert response_payload(response) == {
        "ok": True,
        "mcp": "/mcp",
        "codexCdp": "http://127.0.0.1:9999",
    }


def test_handler_dispatches_and_converts_tool_results() -> None:
    bridge = FakeBridge()
    handler = MCPRequestsHandler(_codex_app_bridge=cast("CodexAppBridge", bridge))

    initialize = run(
        handler.handle_mcp_jsonrpc_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                id="init",
                method="initialize",
                params={"protocolVersion": "2025-03-26"},
            ),
        ),
    )
    assert isinstance(initialize, JSONRPCResponse)
    assert initialize.result["protocolVersion"] == "2025-03-26"

    fallback_initialize = run(
        handler.handle_mcp_jsonrpc_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                id="init-2",
                method="initialize",
                params={"protocolVersion": "unknown"},
            ),
        ),
    )
    assert isinstance(fallback_initialize, JSONRPCResponse)
    assert fallback_initialize.result["protocolVersion"] == MCP_PROTOCOL_VERSION

    none_initialize = run(
        handler.handle_mcp_jsonrpc_message(
            JSONRPCRequest(jsonrpc="2.0", id="init-3", method="initialize", params=None),
        ),
    )
    assert isinstance(none_initialize, JSONRPCResponse)
    assert none_initialize.result["protocolVersion"] == MCP_PROTOCOL_VERSION

    assert (
        run(
            handler.handle_mcp_jsonrpc_message(
                JSONRPCNotification(jsonrpc="2.0", method="notifications/initialized"),
            ),
        )
        is None
    )

    ping = run(
        handler.handle_mcp_jsonrpc_message(JSONRPCRequest(jsonrpc="2.0", id="ping", method="ping")),
    )
    assert isinstance(ping, JSONRPCResponse)
    assert ping.result == {}

    tools = run(
        handler.handle_mcp_jsonrpc_message(
            JSONRPCRequest(jsonrpc="2.0", id="tools", method="tools/list"),
        ),
    )
    assert isinstance(tools, JSONRPCResponse)
    assert tools.result == {"tools": [{"name": "codex_app.echo"}]}

    call = run(
        handler.handle_mcp_jsonrpc_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                id="call",
                method="tools/call",
                params={"name": "echo", "arguments": {"value": 1}},
            ),
        ),
    )
    assert isinstance(call, JSONRPCResponse)
    assert call.result == {
        "content": [{"type": "text", "text": "echo:{'value': 1}"}],
        "isError": False,
    }
    assert bridge.calls == [("echo", {"value": 1})]


def test_handler_reports_jsonrpc_errors() -> None:
    handler = MCPRequestsHandler(_codex_app_bridge=cast("CodexAppBridge", FakeBridge()))

    cases = [
        (
            JSONRPCRequest(jsonrpc="2.0", id="missing", method="missing"),
            -32601,
            "Method not found: missing",
        ),
        (
            JSONRPCRequest(
                jsonrpc="2.0",
                id="bad-name",
                method="tools/call",
                params={"name": ""},
            ),
            -32602,
            "tools/call params.name must be a non-empty string",
        ),
        (
            JSONRPCRequest(
                jsonrpc="2.0",
                id="bad-params",
                method="tools/call",
                params=None,
            ),
            -32602,
            "tools/call params must be an object",
        ),
        (
            JSONRPCRequest(
                jsonrpc="2.0",
                id="bad-arguments",
                method="tools/call",
                params={"name": "echo", "arguments": []},
            ),
            -32602,
            "tools/call params.arguments must be an object",
        ),
        (
            JSONRPCRequest(
                jsonrpc="2.0",
                id="none-arguments",
                method="tools/call",
                params={"name": "echo", "arguments": None},
            ),
            None,
            "",
        ),
        (
            JSONRPCRequest(
                jsonrpc="2.0",
                id="runtime",
                method="tools/call",
                params={"name": "runtime-error"},
            ),
            -32603,
            "boom",
        ),
    ]

    for request, code, message in cases:
        response = run(handler.handle_mcp_jsonrpc_message(request))
        if code is None:
            assert isinstance(response, JSONRPCResponse)
            assert response.result["isError"] is False
            continue
        assert isinstance(response, JSONRPCError)
        assert response.error.code == code
        assert response.error.message == message

    assert (
        run(
            handler.handle_mcp_jsonrpc_message(
                JSONRPCNotification(jsonrpc="2.0", method="missing"),
            ),
        )
        is None
    )


def test_result_adapter_content_shapes() -> None:
    adapter = MCPResultAdapter()

    assert adapter.content_item({"value": 1}) == {"type": "text", "text": '{"value": 1}'}
    assert adapter.adapt({"content": "hello", "isError": True}) == {
        "content": [{"type": "text", "text": "hello"}],
        "isError": True,
    }
    existing = [{"type": "text", "text": "already converted"}]
    assert adapter.adapt({"content": existing}) == {"content": existing, "isError": False}
    assert adapter.adapt({
        "contentItems": ["raw", {"type": "inputText", "text": "typed"}],
    }) == {
        "content": [{"type": "text", "text": "raw"}, {"type": "text", "text": "typed"}],
        "isError": False,
    }
    assert adapter.adapt({
        "contentItems": [{"text": "plain"}, {"value": 1}],
        "success": False,
    }) == {
        "content": [
            {"type": "text", "text": "plain"},
            {"type": "text", "text": '{"value": 1}'},
        ],
        "isError": True,
    }
    assert adapter.adapt({"value": 1}) == {
        "content": [{"type": "text", "text": '{"value": 1}'}],
        "isError": False,
    }
