from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from diwire import Injected
from mcp.types import JSONRPCNotification, JSONRPCRequest

from acodex.core.codex_app.bridge import CodexAppBridge
from acodex.http.mcp.constants import MCP_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from acodex.http.mcp.result_adapter import MCPResultAdapter


class MethodNotFoundError(ValueError):
    """Raised when an MCP method is unknown."""


@dataclass(kw_only=True, slots=True)
class MCPDispatcher:
    """Dispatch JSON-RPC MCP requests to Codex app operations."""

    codex_app_bridge: Injected[CodexAppBridge]
    result_adapter: MCPResultAdapter = field(default_factory=MCPResultAdapter)

    async def dispatch(
        self,
        message: JSONRPCRequest | JSONRPCNotification,
    ) -> dict[str, Any]:
        """Return a JSON-RPC result payload for one message."""
        if message.method == "initialize":
            return InitializeResult().from_params(message.params)
        if message.method == "notifications/initialized":
            return {}
        if message.method == "ping":
            return {}
        if message.method == "tools/list":
            return await self._tools_list()
        if message.method == "tools/call":
            return await self._tools_call(message.params)
        raise MethodNotFoundError(f"Method not found: {message.method}")

    async def _tools_list(self) -> dict[str, Any]:
        tools = await self.codex_app_bridge.list_tools()
        return {"tools": tools}

    async def _tools_call(self, call_params: Any) -> dict[str, Any]:
        params = ToolsCallParams.from_raw(call_params)
        codex_result = await self.codex_app_bridge.call_tool(params.name, params.arguments)
        return self.result_adapter.adapt(codex_result)


@dataclass(frozen=True, slots=True)
class InitializeResult:
    """Build MCP initialize responses."""

    def from_params(self, raw_params: Any) -> dict[str, Any]:
        """Return initialize result for requested protocol params."""
        requested_version = None
        if isinstance(raw_params, dict):
            params_payload = cast("dict[str, Any]", raw_params)
            requested_version = params_payload.get("protocolVersion")
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
                "name": "acodex-app-mcp",
                "version": "0.1.0",
            },
            "instructions": (
                "Exposes the live Codex desktop app codex_app tool namespace over MCP. "
                "The server proxies calls to Codex app handlers through the running renderer."
            ),
        }


@dataclass(frozen=True, slots=True)
class ToolsCallParams:
    """Validated params for tools/call."""

    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_raw(cls, raw_params: Any) -> ToolsCallParams:
        """Validate and return tools/call params."""
        if not isinstance(raw_params, dict):
            raise TypeError("tools/call params must be an object")
        params_payload = cast("dict[str, Any]", raw_params)
        tool_name = params_payload.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("tools/call params.name must be a non-empty string")
        raw_arguments: Any = (
            params_payload.get("arguments") if "arguments" in params_payload else {}
        )
        if raw_arguments is None:
            raw_arguments = {}
        if not isinstance(raw_arguments, dict):
            raise TypeError("tools/call params.arguments must be an object")
        return cls(name=tool_name, arguments=cast("dict[str, Any]", raw_arguments))
