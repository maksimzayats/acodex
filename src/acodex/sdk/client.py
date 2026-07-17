from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from mcp.types import Tool

from acodex.sdk._runtime import McpSessionRuntime
from acodex.sdk.errors import AcodexResultError, AcodexToolError
from acodex.sdk.models import DEFAULT_MCP_URL, DEFAULT_TIMEOUT, ToolResult


@dataclass(kw_only=True, slots=True)
class AsyncAcodexClient:
    """Async public SDK client for an acodex MCP endpoint."""

    mcp_url: str = DEFAULT_MCP_URL
    timeout: float = DEFAULT_TIMEOUT
    _runtime: McpSessionRuntime = field(init=False)

    def __post_init__(self) -> None:
        self._runtime = McpSessionRuntime(mcp_url=self.mcp_url, timeout=self.timeout)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open and initialize the MCP client session."""
        await self._runtime.connect()

    async def close(self) -> None:
        """Close the MCP client session."""
        await self._runtime.close()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return tool descriptors exposed by the acodex MCP server."""
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            result = await self._runtime.list_tools_page(cursor)
            tools.extend(_tool_payload(tool) for tool in result.tools)
            if result.nextCursor is None:
                return tools
            cursor = result.nextCursor

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Call an MCP tool and return a parsed SDK result."""
        result = await self._runtime.call_tool(name, arguments)
        tool_result = ToolResult.from_mcp(result)
        if tool_result.is_error:
            raise AcodexToolError(_tool_error_message(tool_result), result=tool_result)
        return tool_result

    async def call_text(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """Call a tool and return joined text content."""
        return (await self.call_tool(name, arguments)).text()

    async def call_json(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool and return a JSON object from structured or text content."""
        return (await self.call_tool(name, arguments)).json_object()


def _tool_payload(tool: Tool) -> dict[str, Any]:
    return tool.model_dump(mode="json", by_alias=True, exclude_none=True)


def _tool_error_message(tool_result: ToolResult) -> str:
    try:
        return tool_result.text()
    except AcodexResultError:
        return "MCP tool returned an error"
