from dataclasses import dataclass
from typing import Any

from diwire import Injected
from mcp import JSONRPCResponse, JSONRPCError, ErrorData
from mcp.types import JSONRPCNotification, JSONRPCRequest

from acodex.core.codex_app.bridge import CodexAppBridge


MCP_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}


@dataclass(slots=True, kw_only=True)
class MCPRequestsHandler:
    _codex_app_bridge: Injected[CodexAppBridge]

    async def handle_mcp_jsonrpc_message(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
    ) -> JSONRPCResponse | JSONRPCError | JSONRPCNotification | None:
        try:
            if message.method == "initialize":
                result = self._get_initialize_result(params=message.params)
            elif message.method == "notifications/initialized":
                return None
            elif message.method == "ping":
                result = {}
            elif message.method == "tools/list":
                result = await self._tools_list()
            elif message.method == "tools/call":
                result = await self._tools_call(params=message.params)
            else:
                if isinstance(message, JSONRPCNotification):
                    return None

                return JSONRPCError(
                    jsonrpc="2.0",
                    id=message.id,
                    error=ErrorData(
                        code=-32601,
                        message=f"Method not found: {message.method}",
                    ),
                )
        except ValueError as exc:
            if isinstance(message, JSONRPCNotification):
                return None

            return JSONRPCError(
                jsonrpc="2.0",
                id=message.id,
                error=ErrorData(
                    code=-32602,
                    message=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as JSON-RPC internal error.
            if isinstance(message, JSONRPCNotification):
                return None

            return JSONRPCError(
                jsonrpc="2.0",
                id=message.id,
                error=ErrorData(
                    code=-32603,
                    message=str(exc),
                )
            )

        if isinstance(message, JSONRPCNotification):
            return None

        return JSONRPCResponse(
            jsonrpc="2.0",
            id=message.id,
            result=result,
        )

    @staticmethod
    def _get_initialize_result(params: Any) -> dict[str, Any]:
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version if requested_version in SUPPORTED_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSION
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
        ...

    async def _tools_call(self, params: Any) -> dict[str, Any]:
        ...
