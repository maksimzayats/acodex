from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, ClassVar, NoReturn, cast

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import StreamableHTTPError, streamable_http_client
from mcp.shared.exceptions import McpError
from mcp.types import CONNECTION_CLOSED, Implementation, ListToolsResult, PaginatedRequestParams

from acodex.sdk.errors import AcodexConnectionError, AcodexToolError

SDK_CLIENT_NAME = "acodex-sdk"
SDK_CLIENT_VERSION = "0"


@dataclass(kw_only=True, slots=True)
class McpSessionRuntime:
    """Own MCP session lifecycle and transport error normalization."""

    transport_errors: ClassVar[tuple[type[Exception], ...]] = (
        StreamableHTTPError,
        httpx.HTTPError,
        OSError,
        TimeoutError,
    )
    session_errors: ClassVar[tuple[type[Exception], ...]] = (*transport_errors, McpError)
    open_connection_errors: ClassVar[tuple[type[Exception], ...]] = (
        *session_errors,
        RuntimeError,
    )
    operation_base_errors: ClassVar[tuple[type[BaseException], ...]] = (
        asyncio.CancelledError,
        BaseExceptionGroup,
    )
    cleanup_errors: ClassVar[tuple[type[BaseException], ...]] = (
        *open_connection_errors,
        asyncio.CancelledError,
        BaseExceptionGroup,
    )
    connection_error_codes: ClassVar[frozenset[int]] = frozenset(
        (CONNECTION_CLOSED, httpx.codes.REQUEST_TIMEOUT),
    )

    mcp_url: str
    timeout: float
    _exit_stack: AsyncExitStack | None = field(default=None, init=False)
    _lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _session: ClientSession | None = field(default=None, init=False)

    async def connect(self) -> None:
        """Open and initialize the MCP client session."""
        async with self._lifecycle_lock:
            if self._session is not None:
                return
            exit_stack = AsyncExitStack()
            try:
                self._session = await self._open_session(exit_stack)
                self._exit_stack = exit_stack
            except BaseExceptionGroup as exc:
                await self._raise_open_error(exit_stack, exc)
            except self.open_connection_errors as exc:
                await self._raise_open_error(exit_stack, exc)
            except asyncio.CancelledError as exc:
                cleanup_exc = await self._clear_after_failed_open(exit_stack)
                if cleanup_exc is not None and _is_internal_cancel(exc):
                    _raise_connect_error(self.mcp_url, cleanup_exc)
                raise

    async def close(self) -> None:
        """Close the MCP client session."""
        async with self._lifecycle_lock:
            exit_stack = self._exit_stack
            self._clear_session()
            if exit_stack is not None:
                await exit_stack.aclose()

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None,
    ) -> Any:
        """Call an MCP tool through the active session."""
        message = f"Could not call MCP tool {name!r} at {self.mcp_url}"
        try:
            return await self._session_or_raise().call_tool(
                name,
                arguments or {},
                read_timeout_seconds=timedelta(seconds=self.timeout),
            )
        except McpError as exc:
            if _is_mcp_connection_error(exc):
                await self._raise_operation_connection_error(message, exc)
            raise AcodexToolError(str(exc), code=exc.error.code, data=exc.error.data) from exc
        except self.operation_base_errors as exc:
            await self._raise_base_operation_error(message, exc)
        except self.transport_errors as exc:
            await self._raise_operation_connection_error(message, exc)

    async def list_tools_page(self, cursor: str | None) -> ListToolsResult:
        """Return one MCP tools/list page."""
        try:
            return await self._session_or_raise().list_tools(
                params=PaginatedRequestParams(cursor=cursor),
            )
        except McpError as exc:
            if _is_mcp_connection_error(exc):
                await self._raise_operation_connection_error("Could not list MCP tools", exc)
            raise AcodexToolError(str(exc), code=exc.error.code, data=exc.error.data) from exc
        except self.operation_base_errors as exc:
            await self._raise_base_operation_error("Could not list MCP tools", exc)
        except self.transport_errors as exc:
            await self._raise_operation_connection_error(
                f"Could not reach acodex MCP server at {self.mcp_url}",
                exc,
            )

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

    def _session_or_raise(self) -> ClientSession:
        if self._session is None:
            raise AcodexConnectionError(
                "AsyncAcodexClient is not connected; use `async with AsyncAcodexClient(...)`.",
            )
        return self._session

    def _clear_session(self) -> None:
        self._session = None
        self._exit_stack = None

    async def _clear_after_failed_open(self, exit_stack: AsyncExitStack) -> BaseException | None:
        try:
            await exit_stack.aclose()
        except self.cleanup_errors as exc:
            self._clear_session()
            return _connection_cause(exc)
        self._clear_session()
        return None

    async def _close_failed_session(self) -> BaseException | None:
        async with self._lifecycle_lock:
            exit_stack = self._exit_stack
            self._clear_session()
        if exit_stack is None:
            return None
        try:
            await exit_stack.aclose()
        except self.cleanup_errors as exc:
            return _connection_cause(exc)
        return None

    async def _raise_open_error(
        self,
        exit_stack: AsyncExitStack,
        exc: BaseException,
    ) -> NoReturn:
        cleanup_exc = await self._clear_after_failed_open(exit_stack)
        connection_exc = _connection_cause(exc) or cleanup_exc or exc
        _raise_connect_error(self.mcp_url, connection_exc)

    async def _raise_base_operation_error(
        self,
        message: str,
        exc: BaseException,
    ) -> NoReturn:
        cleanup_exc = await self._close_failed_session()
        if isinstance(exc, asyncio.CancelledError) and not _is_internal_cancel(exc):
            raise exc
        connection_exc = cleanup_exc or _connection_cause(exc)
        if connection_exc is not None:
            raise AcodexConnectionError(f"{message}: {connection_exc}") from connection_exc
        raise exc

    async def _raise_operation_connection_error(
        self,
        message: str,
        exc: BaseException,
    ) -> NoReturn:
        cleanup_exc = await self._close_failed_session()
        connection_exc = cleanup_exc or _connection_cause(exc) or exc
        raise AcodexConnectionError(f"{message}: {connection_exc}") from connection_exc


def _is_mcp_connection_error(exc: McpError) -> bool:
    return exc.error.code in McpSessionRuntime.connection_error_codes


def _raise_connect_error(mcp_url: str, exc: BaseException) -> NoReturn:
    raise AcodexConnectionError(
        f"Could not connect to acodex MCP server at {mcp_url}: {exc}",
    ) from exc


def _is_internal_cancel(exc: asyncio.CancelledError) -> bool:
    return "cancel scope" in str(exc)


def _connection_cause(exc: BaseException) -> BaseException | None:
    if isinstance(exc, McpError) and _is_mcp_connection_error(exc):
        return exc
    if isinstance(exc, McpSessionRuntime.transport_errors):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        group_exc = cast("BaseExceptionGroup[BaseException]", exc)  # type: ignore[redundant-cast]
        return _connection_group_cause(group_exc)
    return None


def _connection_group_cause(exc: BaseExceptionGroup[Any]) -> BaseException | None:
    for nested_exc in exc.exceptions:
        connection_exc = _connection_cause(nested_exc)
        if connection_exc is not None:
            return connection_exc
    return None
