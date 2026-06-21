from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

from mcp import JSONRPCError, JSONRPCRequest, JSONRPCResponse
from mcp.types import JSONRPCNotification
from pydantic import TypeAdapter, ValidationError
from starlette import status
from starlette.responses import Response

from acodex.http.mcp.constants import (
    JSONRPC_INVALID_REQUEST,
    JSONRPC_VERSION,
    MCP_PROTOCOL_VERSION,
)


@dataclass(frozen=True, slots=True)
class JSONRPCCodec:
    """Validate JSON-RPC messages and build JSON responses."""

    request_adapter: TypeAdapter[JSONRPCRequest] = field(
        default_factory=lambda: TypeAdapter(JSONRPCRequest),
    )
    notification_adapter: TypeAdapter[JSONRPCNotification] = field(
        default_factory=lambda: TypeAdapter(JSONRPCNotification),
    )

    def validate(self, raw_message: Any) -> JSONRPCRequest | JSONRPCNotification | dict[str, Any]:
        """Return a typed JSON-RPC message or raw JSON-RPC error payload."""
        if not isinstance(raw_message, dict):
            return self.raw_error(None, code=JSONRPC_INVALID_REQUEST, message="Invalid Request")
        message_payload = cast("dict[str, Any]", raw_message)

        try:
            return self._validate_object(message_payload)
        except ValidationError:
            return self.raw_error(
                self.response_id(message_payload.get("id")),
                code=JSONRPC_INVALID_REQUEST,
                message="Invalid Request",
            )

    def response_payload(self, response: JSONRPCResponse | JSONRPCError) -> dict[str, Any]:
        """Return the JSON-compatible response payload."""
        return response.model_dump(mode="json", exclude_none=True)

    def raw_error(
        self,
        message_id: str | int | None,
        *,
        code: int,
        message: str,
    ) -> dict[str, Any]:
        """Return a raw JSON-RPC error payload."""
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": message_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

    def jsonrpc_response(self, json_payload: Any) -> Response:
        """Return a JSON-RPC response with MCP protocol header."""
        return self.json_response(
            json_payload,
            headers={"MCP-Protocol-Version": MCP_PROTOCOL_VERSION},
        )

    def json_response(
        self,
        json_payload: Any,
        *,
        status_code: int = status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Return a JSON response."""
        return Response(
            content=json.dumps(json_payload, ensure_ascii=False),
            status_code=status_code,
            headers=headers,
            media_type="application/json",
        )

    def response_id(self, message_id: Any) -> str | int | None:
        """Return a JSON-RPC-compatible id."""
        if isinstance(message_id, bool):
            return None
        if isinstance(message_id, (str, int)):
            return message_id
        return None

    def _validate_object(self, raw_message: dict[str, Any]) -> JSONRPCRequest | JSONRPCNotification:
        if "id" in raw_message:
            return self.request_adapter.validate_python(raw_message)
        return self.notification_adapter.validate_python(raw_message)
