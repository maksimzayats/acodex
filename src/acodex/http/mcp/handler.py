from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from diwire import Injected
from mcp import ErrorData, JSONRPCError, JSONRPCResponse
from mcp.types import JSONRPCNotification, JSONRPCRequest

from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.http.mcp.constants import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_VERSION,
    MCP_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from acodex.http.mcp.dispatcher import MCPDispatcher, MethodNotFoundError
from acodex.http.mcp.result_adapter import _codex_result_to_mcp, _content_item_to_mcp


@dataclass(kw_only=True, slots=True)
class MCPRequestsHandler:
    """Handle single MCP JSON-RPC messages."""

    _codex_app_bridge: Injected[CodexAppBridge]
    _dispatcher: MCPDispatcher | None = field(default=None, init=False)

    async def handle_mcp_jsonrpc_message(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
    ) -> JSONRPCResponse | JSONRPCError | None:
        """Handle a single MCP JSON-RPC request or notification."""
        try:
            response_result = await self._get_dispatcher().dispatch(message)
        except MethodNotFoundError as exc:
            return self._error_response(
                message,
                code=JSONRPC_METHOD_NOT_FOUND,
                message_text=str(exc),
            )
        except (ValueError, TypeError) as exc:
            return self._error_response(message, code=JSONRPC_INVALID_PARAMS, message_text=str(exc))
        except Exception as exc:  # noqa: BLE001 - surfaced as JSON-RPC internal error.
            return self._error_response(message, code=JSONRPC_INTERNAL_ERROR, message_text=str(exc))

        return self._success_response(message, response_result)

    def _get_dispatcher(self) -> MCPDispatcher:
        if self._dispatcher is None:
            self._dispatcher = MCPDispatcher(codex_app_bridge=self._codex_app_bridge)
        return self._dispatcher

    def _success_response(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
        response_result: dict[str, Any],
    ) -> JSONRPCResponse | None:
        if isinstance(message, JSONRPCNotification):
            return None
        return JSONRPCResponse(
            jsonrpc=JSONRPC_VERSION,
            id=message.id,
            result=response_result,
        )

    def _error_response(
        self,
        jsonrpc_message: JSONRPCRequest | JSONRPCNotification,
        *,
        code: int,
        message_text: str,
    ) -> JSONRPCError | None:
        if isinstance(jsonrpc_message, JSONRPCNotification):
            return None
        return JSONRPCError(
            jsonrpc=JSONRPC_VERSION,
            id=jsonrpc_message.id,
            error=ErrorData(code=code, message=message_text),
        )


__all__ = (
    "MCP_PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "MCPRequestsHandler",
    "_codex_result_to_mcp",
    "_content_item_to_mcp",
)
