from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from diwire import Injected, Scope, resolver_context
from fastapi import APIRouter, Request, Response
from mcp import JSONRPCError, JSONRPCRequest, JSONRPCResponse
from mcp.types import JSONRPCNotification
from pydantic import TypeAdapter, ValidationError
from starlette import status

from acodex.core.codex_app.cdp import CodexCDPSettings
from acodex.http.mcp.handler import MCP_PROTOCOL_VERSION, MCPRequestsHandler

mcp_router = APIRouter(tags=["MCP"])
_request_adapter: TypeAdapter[JSONRPCRequest] = TypeAdapter(JSONRPCRequest)
_notification_adapter: TypeAdapter[JSONRPCNotification] = TypeAdapter(JSONRPCNotification)


@mcp_router.get("/healthz")
@resolver_context.inject(scope=Scope.REQUEST)
async def healthz(
    *,
    cdp_settings: Injected[CodexCDPSettings],
) -> Response:
    return _json_response(
        {
            "ok": True,
            "mcp": "/mcp",
            "codexCdp": cdp_settings.base_url,
        },
    )


@mcp_router.post("/mcp")
@resolver_context.inject(scope=Scope.REQUEST)
async def handle_mcp(
    request: Request,
    *,
    handler: Injected[MCPRequestsHandler],
) -> Response:
    if not _is_allowed_origin(request):
        return _json_response({"error": "forbidden origin"}, status_code=status.HTTP_403_FORBIDDEN)

    try:
        request_data = await request.json()
    except json.JSONDecodeError:
        return _jsonrpc_response(_raw_error(None, code=-32700, message="Parse error"))

    if isinstance(request_data, list):
        return await _handle_batch(request_data, handler)

    return await _handle_single(request_data, handler)


async def _handle_batch(raw_messages: list[Any], handler: MCPRequestsHandler) -> Response:
    if not raw_messages:
        return _jsonrpc_response(_raw_error(None, code=-32600, message="Invalid Request"))

    responses: list[Any] = []
    for raw_data in raw_messages:
        data = _validate_message(raw_data)
        if isinstance(data, dict):
            responses.append(data)
            continue
        response = await handler.handle_mcp_jsonrpc_message(data)
        if response is not None:
            responses.append(_response_payload(response))

    if responses:
        return _jsonrpc_response(responses)

    return Response(status_code=status.HTTP_202_ACCEPTED)


async def _handle_single(raw_message: Any, handler: MCPRequestsHandler) -> Response:
    data = _validate_message(raw_message)
    if isinstance(data, dict):
        return _jsonrpc_response(data)

    response = await handler.handle_mcp_jsonrpc_message(data)

    if response:
        return _jsonrpc_response(_response_payload(response))

    return Response(status_code=status.HTTP_202_ACCEPTED)


def _validate_message(raw_data: Any) -> JSONRPCRequest | JSONRPCNotification | dict[str, Any]:
    if not isinstance(raw_data, dict):
        return _raw_error(None, code=-32600, message="Invalid Request")

    try:
        if "id" in raw_data:
            return _request_adapter.validate_python(raw_data)
        return _notification_adapter.validate_python(raw_data)
    except ValidationError:
        return _raw_error(_response_id(raw_data.get("id")), code=-32600, message="Invalid Request")


def _response_payload(response: JSONRPCResponse | JSONRPCError) -> dict[str, Any]:
    return response.model_dump(mode="json", exclude_none=True)


def _raw_error(message_id: str | int | None, *, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _response_id(message_id: Any) -> str | int | None:
    if isinstance(message_id, bool):
        return None
    if isinstance(message_id, (str, int)):
        return message_id
    return None


def _jsonrpc_response(payload: Any) -> Response:
    return _json_response(payload, headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION})


def _json_response(
    payload: Any,
    *,
    status_code: int = status.HTTP_200_OK,
    headers: dict[str, str] | None = None,
) -> Response:
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        headers=headers,
        media_type="application/json",
    )


def _is_allowed_origin(request: Request) -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
