from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Self, TypeAlias

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import StreamableHTTPError, streamable_http_client
from mcp.shared.exceptions import McpError
from mcp.types import (
    CONNECTION_CLOSED,
    Implementation,
    ListToolsResult,
    PaginatedRequestParams,
    Tool,
)

from acodex.sdk.errors import AcodexConnectionError, AcodexResultError, AcodexToolError
from acodex.sdk.models import DEFAULT_MCP_URL, DEFAULT_TIMEOUT, ToolResult

SDK_CLIENT_NAME = "acodex-sdk"
SDK_CLIENT_VERSION = "0"
ErrorTypes: TypeAlias = tuple[type[Exception], ...]
TRANSPORT_ERRORS: ErrorTypes = (
    StreamableHTTPError,
    httpx.HTTPError,
    OSError,
    TimeoutError,
)
SESSION_ERRORS: ErrorTypes = (*TRANSPORT_ERRORS, McpError)
MCP_CONNECTION_ERROR_CODES = frozenset({CONNECTION_CLOSED, httpx.codes.REQUEST_TIMEOUT})


@dataclass(kw_only=True, slots=True)
class AsyncAcodexClient:
    """Async public SDK client for an acodex MCP endpoint."""

    mcp_url: str = DEFAULT_MCP_URL
    timeout: float = DEFAULT_TIMEOUT
    _exit_stack: AsyncExitStack | None = field(default=None, init=False)
    _lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _session: ClientSession | None = field(default=None, init=False)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open and initialize the MCP client session."""
        async with self._lifecycle_lock:
            if self._session is not None:
                return

            exit_stack = AsyncExitStack()
            try:
                self._session = await self._open_session(exit_stack)
                self._exit_stack = exit_stack
            except SESSION_ERRORS as exc:
                await exit_stack.aclose()
                self._clear_session()
                raise AcodexConnectionError(
                    f"Could not connect to acodex MCP server at {self.mcp_url}: {exc}",
                ) from exc
            except BaseException:
                await exit_stack.aclose()
                self._clear_session()
                raise

    async def close(self) -> None:
        """Close the MCP client session."""
        async with self._lifecycle_lock:
            exit_stack = self._exit_stack
            self._clear_session()
            if exit_stack is not None:
                await exit_stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return tool descriptors exposed by the acodex MCP server."""
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            result = await self._list_tools_page(cursor)
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
        session = self._session_or_raise()
        try:
            result = await session.call_tool(
                name,
                arguments or {},
                read_timeout_seconds=timedelta(seconds=self.timeout),
            )
        except McpError as exc:
            if _is_mcp_connection_error(exc):
                raise AcodexConnectionError(
                    f"Could not call MCP tool {name!r} at {self.mcp_url}: {exc}",
                ) from exc
            raise AcodexToolError(
                str(exc),
                code=exc.error.code,
                data=exc.error.data,
            ) from exc
        except TRANSPORT_ERRORS as exc:
            raise AcodexConnectionError(
                f"Could not call MCP tool {name!r} at {self.mcp_url}: {exc}",
            ) from exc

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

    async def _open_session(self, exit_stack: AsyncExitStack) -> ClientSession:
        http_client = await exit_stack.enter_async_context(
            httpx.AsyncClient(timeout=self.timeout),
        )
        read_stream, write_stream, _session_id = await exit_stack.enter_async_context(
            streamable_http_client(self.mcp_url, http_client=http_client),
        )
        session = ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=self.timeout),
            client_info=Implementation(name=SDK_CLIENT_NAME, version=SDK_CLIENT_VERSION),
        )
        initialized_session = await exit_stack.enter_async_context(session)
        await initialized_session.initialize()
        return initialized_session

    async def _list_tools_page(self, cursor: str | None) -> ListToolsResult:
        session = self._session_or_raise()
        try:
            return await session.list_tools(
                params=PaginatedRequestParams(cursor=cursor),
            )
        except McpError as exc:
            if _is_mcp_connection_error(exc):
                raise AcodexConnectionError(f"Could not list MCP tools: {exc}") from exc
            raise AcodexToolError(
                str(exc),
                code=exc.error.code,
                data=exc.error.data,
            ) from exc
        except TRANSPORT_ERRORS as exc:
            raise AcodexConnectionError(
                f"Could not reach acodex MCP server at {self.mcp_url}: {exc}",
            ) from exc

    def _session_or_raise(self) -> ClientSession:
        if self._session is None:
            raise AcodexConnectionError(
                "AsyncAcodexClient is not connected; use `async with AsyncAcodexClient(...)`.",
            )
        return self._session

    def _clear_session(self) -> None:
        self._session = None
        self._exit_stack = None


def _tool_payload(tool: Tool) -> dict[str, Any]:
    return tool.model_dump(mode="json", by_alias=True, exclude_none=True)


def _tool_error_message(tool_result: ToolResult) -> str:
    try:
        return tool_result.text()
    except AcodexResultError:
        return "MCP tool returned an error"


def _is_mcp_connection_error(exc: McpError) -> bool:
    return exc.error.code in MCP_CONNECTION_ERROR_CODES
