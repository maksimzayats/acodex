from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from diwire import Injected
from mcp import ErrorData, JSONRPCError, JSONRPCResponse
from mcp.types import JSONRPCNotification, JSONRPCRequest

from acodex.core.codex_app.bridge import CodexAppBridge

MCP_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}


class _MethodNotFoundError(ValueError):
    def __init__(self, method: str) -> None:
        self.method = method
        super().__init__(f"Method not found: {method}")


@dataclass(slots=True, kw_only=True)
class MCPRequestsHandler:
    _codex_app_bridge: Injected[CodexAppBridge]

    async def handle_mcp_jsonrpc_message(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
    ) -> JSONRPCResponse | JSONRPCError | JSONRPCNotification | None:
        """Handle a single MCP JSON-RPC request or notification.

        Returns:
            A JSON-RPC response for requests, or None for notifications.

        """
        try:  # refactor later
            result = await self._dispatch_message(message)
        except _MethodNotFoundError as exc:
            return self._error_response(
                jsonrpc_message=message,
                code=-32601,
                message_text=str(exc),
            )
        except ValueError as exc:
            return self._error_response(
                jsonrpc_message=message,
                code=-32602,
                message_text=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as JSON-RPC internal error.
            return self._error_response(
                jsonrpc_message=message,
                code=-32603,
                message_text=str(exc),
            )

        return self._success_response(message=message, result=result)

    async def _dispatch_message(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
    ) -> dict[str, Any]:
        if message.method == "initialize":
            return self._get_initialize_result(params=message.params)
        if message.method == "notifications/initialized":
            return {}
        if message.method == "ping":
            return {}
        if message.method == "tools/list":
            return await self._tools_list()
        if message.method == "tools/call":
            return await self._tools_call(params=message.params)

        raise _MethodNotFoundError(message.method)

    @staticmethod
    def _success_response(
        message: JSONRPCRequest | JSONRPCNotification,
        result: dict[str, Any],
    ) -> JSONRPCResponse | None:
        if isinstance(message, JSONRPCNotification):
            return None

        return JSONRPCResponse(
            jsonrpc="2.0",
            id=message.id,
            result=result,
        )

    @staticmethod
    def _error_response(
        *,
        jsonrpc_message: JSONRPCRequest | JSONRPCNotification,
        code: int,
        message_text: str,
    ) -> JSONRPCError | None:
        if isinstance(jsonrpc_message, JSONRPCNotification):
            return None

        return JSONRPCError(
            jsonrpc="2.0",
            id=jsonrpc_message.id,
            error=ErrorData(
                code=code,
                message=message_text,
            ),
        )

    @staticmethod
    def _get_initialize_result(params: Any) -> dict[str, Any]:
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version
            if requested_version in SUPPORTED_PROTOCOL_VERSIONS
            else MCP_PROTOCOL_VERSION
        )
        return {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": True},
            },
            "serverInfo": {
                "name": "o3-os-codex-app-mcp",
                "version": "0.1.0",
            },
            "instructions": (
                "Exposes the live Codex desktop app codex_app tool namespace over MCP. "
                "The server proxies calls to Codex app handlers through the running renderer."
            ),
        }

    async def _tools_list(self) -> dict[str, Any]:
        raise NotImplementedError

    async def _tools_call(self, params: Any) -> dict[str, Any]:
        raise NotImplementedError
