from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, cast

from diwire import Injected, Scope, resolver_context
from fastapi import APIRouter, Request
from mcp.types import JSONRPCNotification, JSONRPCRequest
from starlette import status
from starlette.responses import Response

from acodex.core.codex_app.cdp import CodexCDPSettings
from acodex.http.mcp.codec import JSONRPCCodec
from acodex.http.mcp.constants import JSONRPC_INVALID_REQUEST, JSONRPC_PARSE_ERROR
from acodex.http.mcp.handler import MCPRequestsHandler
from acodex.http.mcp.security import OriginPolicy

mcp_router = APIRouter(tags=["MCP"])


@mcp_router.get("/healthz")
@resolver_context.inject(scope=Scope.REQUEST)
async def healthz(
    *,
    cdp_settings: Injected[CodexCDPSettings],
) -> Response:
    return JSONRPCCodec().json_response(
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
    codec = JSONRPCCodec()
    if not OriginPolicy().allows(request):
        return codec.json_response(
            {"error": "forbidden origin"},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    try:
        request_payload = await request.json()
    except json.JSONDecodeError:
        return codec.jsonrpc_response(
            codec.raw_error(None, code=JSONRPC_PARSE_ERROR, message="Parse error"),
        )

    processor = MCPRequestProcessor(codec=codec, handler=handler)
    return await processor.process(request_payload)


@dataclass(frozen=True, kw_only=True, slots=True)
class MCPRequestProcessor:
    """Process JSON-RPC single and batch requests."""

    codec: JSONRPCCodec = field(default_factory=JSONRPCCodec)
    handler: MCPRequestsHandler

    async def process(self, request_payload: Any) -> Response:
        """Return the response for a raw JSON-RPC payload."""
        if isinstance(request_payload, list):
            messages = cast("list[Any]", request_payload)  # type: ignore[redundant-cast]
            return await self.batch(messages)
        return await self.single(request_payload)

    async def batch(self, raw_messages: list[Any]) -> Response:
        """Return the response for a JSON-RPC batch request."""
        if not raw_messages:
            return self.codec.jsonrpc_response(
                self.codec.raw_error(None, code=JSONRPC_INVALID_REQUEST, message="Invalid Request"),
            )
        response_payloads = await asyncio.gather(
            *(self._message_response(raw_message) for raw_message in raw_messages),
        )
        responses = [payload for payload in response_payloads if payload is not None]
        if responses:
            return self.codec.jsonrpc_response(responses)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    async def single(self, raw_message: Any) -> Response:
        """Return the response for a single JSON-RPC message."""
        response_payload = await self._message_response(raw_message)
        if response_payload is not None:
            return self.codec.jsonrpc_response(response_payload)
        return Response(status_code=status.HTTP_202_ACCEPTED)

    async def _message_response(self, raw_message: Any) -> dict[str, Any] | None:
        validated_message = self.codec.validate(raw_message)
        if isinstance(validated_message, dict):
            return validated_message
        response = await self.handler.handle_mcp_jsonrpc_message(validated_message)
        if response is None:
            return None
        return self.codec.response_payload(response)


async def _handle_batch(raw_messages: list[Any], handler: MCPRequestsHandler) -> Response:
    return await MCPRequestProcessor(handler=handler).batch(raw_messages)


async def _handle_single(raw_message: Any, handler: MCPRequestsHandler) -> Response:
    return await MCPRequestProcessor(handler=handler).single(raw_message)


def _validate_message(raw_message: Any) -> JSONRPCRequest | JSONRPCNotification | dict[str, Any]:
    return JSONRPCCodec().validate(raw_message)


def _response_id(message_id: Any) -> str | int | None:
    return JSONRPCCodec().response_id(message_id)


def _is_allowed_origin(request: Request) -> bool:
    return OriginPolicy().allows(request)


__all__ = (
    "MCPRequestProcessor",
    "_handle_batch",
    "_handle_single",
    "_is_allowed_origin",
    "_response_id",
    "_validate_message",
    "handle_mcp",
    "healthz",
    "mcp_router",
)
