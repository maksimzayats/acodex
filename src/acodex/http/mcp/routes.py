from __future__ import annotations

import json
from typing import Any

from diwire import Injected, Scope, resolver_context
from fastapi import APIRouter, Request, Response
from mcp import ErrorData, JSONRPCError, JSONRPCRequest
from mcp.types import JSONRPCNotification
from pydantic import TypeAdapter
from starlette import status

from acodex.http.mcp.handler import MCP_PROTOCOL_VERSION, MCPRequestsHandler

mcp_router = APIRouter(tags=["MCP"])


@mcp_router.post("/mcp")
@resolver_context.inject(scope=Scope.REQUEST)
async def handle_mcp(
    request: Request,
    *,
    handler: Injected[MCPRequestsHandler],
) -> Response:
    try:
        request_data = await request.json()
    except json.JSONDecodeError:
        error = JSONRPCError.model_construct(
            jsonrpc="2.0",
            id=None,
            error=ErrorData(code=-32700, message="Parse error"),
        )
        return Response(
            content=error.model_dump_json(exclude={"error": {"data"}}),
            status_code=status.HTTP_200_OK,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
            media_type="application/json",
        )

    adapter = TypeAdapter(JSONRPCRequest | JSONRPCNotification)

    if isinstance(request_data, list):
        responses: list[Any] = []
        for raw_data in request_data:
            data = adapter.validate_python(raw_data)
            response = await handler.handle_mcp_jsonrpc_message(data)
            if response is not None:
                responses.append(response.model_dump())

        if responses:
            return Response(
                content=json.dumps(responses, ensure_ascii=False),
                status_code=status.HTTP_200_OK,
                headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
                media_type="application/json",
            )

        return Response(status_code=204)

    data = adapter.validate_python(request_data)
    response = await handler.handle_mcp_jsonrpc_message(data)

    if response:
        return Response(
            content=json.dumps(response, ensure_ascii=False),
            status_code=status.HTTP_200_OK,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
            media_type="application/json",
        )

    return Response(status_code=204)
