from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Protocol, TypeAlias

from typing_extensions import Self, Unpack

from acodex.core.asyncio.cdp.errors import (
    CodexAppCdpConnectionError,
    CodexAppCdpDiscoveryError,
)
from acodex.core.asyncio.cdp.renderer import (
    build_tool_discovery_expression,
    build_tool_invocation_expression,
    parse_tool_discovery_result,
)
from acodex.core.asyncio.cdp.runtime import CdpRuntimeEvaluator, connect_websocket_runtime
from acodex.core.asyncio.cdp.settings import CodexAppCdpSettings
from acodex.core.asyncio.cdp.targets import fetch_cdp_targets, select_codex_app_target
from acodex.core.asyncio.cdp.types import CdpTarget, CodexAppToolDiscovery, JsonObject, JsonValue
from acodex.core.asyncio.tools.create_thread import CreateThreadToolInput, CreateThreadToolOutput
from acodex.core.asyncio.tools.fork_thread import ForkThreadToolInput, ForkThreadToolOutput
from acodex.core.asyncio.tools.handoff_thread import HandoffThreadToolInput, HandoffThreadToolOutput
from acodex.core.asyncio.tools.list_threads import ListThreadsToolInput, ListThreadsToolOutput
from acodex.core.asyncio.tools.read_thread import ReadThreadToolInput, ReadThreadToolOutput
from acodex.core.asyncio.tools.send_message_to_thread import (
    SendMessageToThreadToolInput,
    SendMessageToThreadToolOutput,
)
from acodex.core.asyncio.tools.set_thread_archived import (
    SetThreadArchivedToolInput,
    SetThreadArchivedToolOutput,
)
from acodex.core.asyncio.tools.set_thread_pinned import (
    SetThreadPinnedToolInput,
    SetThreadPinnedToolOutput,
)
from acodex.core.asyncio.tools.set_thread_title import (
    SetThreadTitleToolInput,
    SetThreadTitleToolOutput,
)
from acodex.core.asyncio.tools.thread_tools import CodexAppThreadTools

_TargetFetcher: TypeAlias = Callable[[CodexAppCdpSettings], Awaitable[tuple[CdpTarget, ...]]]


class _RuntimeConnector(Protocol):
    def __call__(
        self,
        websocket_url: str,
        *,
        runtime_timeout: float,
    ) -> Awaitable[CdpRuntimeEvaluator]: ...


class CodexAppCdpClient:
    def __init__(
        self,
        endpoint: str | None = None,
        *,
        settings: CodexAppCdpSettings | None = None,
        target_fetcher: _TargetFetcher | None = None,
        runtime_connector: _RuntimeConnector | None = None,
    ) -> None:
        resolved_settings = settings or CodexAppCdpSettings()
        if endpoint is not None:
            resolved_settings = resolved_settings.model_copy(update={"endpoint": endpoint})
        self.settings = resolved_settings
        self.target: CdpTarget | None = None
        self.tool_discovery: CodexAppToolDiscovery | None = None
        self._target_fetcher = target_fetcher or _fetch_targets_for_settings
        self._runtime_connector = runtime_connector or connect_websocket_runtime
        self._runtime: CdpRuntimeEvaluator | None = None
        self.tools = CodexAppThreadTools.bind(self._invoke_tool)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(  # noqa: PLR0917
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def connect(self) -> Self:
        """Connect to the Codex app renderer and discover thread tools.

        Returns:
            This client after the CDP runtime and tool discovery are ready.

        """
        if self._runtime is not None:
            return self

        targets = await self._target_fetcher(self.settings)
        self.target = select_codex_app_target(
            targets,
            target_url=self.settings.target_url,
            target_url_prefix=self.settings.target_url_prefix,
        )
        self._runtime = await self._runtime_connector(
            self.target.websocket_debugger_url,
            runtime_timeout=self.settings.runtime_timeout,
        )
        discovery_result = await self._runtime.evaluate(build_tool_discovery_expression())
        self.tool_discovery = parse_tool_discovery_result(discovery_result)
        return self

    async def close(self) -> None:
        """Close the underlying CDP websocket when one is open."""
        runtime = self._runtime
        self._runtime = None
        if runtime is not None:
            await runtime.close()

    async def list_threads(
        self,
        **arguments: Unpack[ListThreadsToolInput],
    ) -> ListThreadsToolOutput:
        """List recent Codex desktop threads.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.list_threads(**arguments)

    async def read_thread(
        self,
        **arguments: Unpack[ReadThreadToolInput],
    ) -> ReadThreadToolOutput:
        """Read recent metadata and turns for one Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.read_thread(**arguments)

    async def create_thread(
        self,
        **arguments: Unpack[CreateThreadToolInput],
    ) -> CreateThreadToolOutput:
        """Create a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.create_thread(**arguments)

    async def send_message_to_thread(
        self,
        **arguments: Unpack[SendMessageToThreadToolInput],
    ) -> SendMessageToThreadToolOutput:
        """Send a prompt to an existing Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.send_message_to_thread(**arguments)

    async def fork_thread(
        self,
        *,
        source_thread_id: str,
        **arguments: Unpack[ForkThreadToolInput],
    ) -> ForkThreadToolOutput:
        """Fork a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.fork_thread(source_thread_id=source_thread_id, **arguments)

    async def set_thread_pinned(
        self,
        **arguments: Unpack[SetThreadPinnedToolInput],
    ) -> SetThreadPinnedToolOutput:
        """Pin or unpin a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.set_thread_pinned(**arguments)

    async def set_thread_archived(
        self,
        **arguments: Unpack[SetThreadArchivedToolInput],
    ) -> SetThreadArchivedToolOutput:
        """Archive or unarchive a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.set_thread_archived(**arguments)

    async def set_thread_title(
        self,
        **arguments: Unpack[SetThreadTitleToolInput],
    ) -> SetThreadTitleToolOutput:
        """Rename a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.set_thread_title(**arguments)

    async def handoff_thread(
        self,
        **arguments: Unpack[HandoffThreadToolInput],
    ) -> HandoffThreadToolOutput:
        """Hand off a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self.tools.handoff_thread(**arguments)

    async def _invoke_tool(
        self,
        tool_name: str,
        arguments: JsonObject,
        *,
        source_thread_id: str | None = None,
    ) -> JsonValue:
        if self._runtime is None:
            await self.connect()
        if self.tool_discovery is not None and tool_name not in self.tool_discovery.tool_names:
            raise CodexAppCdpDiscoveryError(f"Codex app tool was not discovered: {tool_name}")

        runtime = self._runtime
        if runtime is None:
            raise CodexAppCdpConnectionError("CDP runtime is not connected")

        return await runtime.evaluate(
            build_tool_invocation_expression(
                tool_name,
                arguments,
                source_thread_id=source_thread_id,
            ),
        )


async def _fetch_targets_for_settings(settings: CodexAppCdpSettings) -> tuple[CdpTarget, ...]:
    return await fetch_cdp_targets(settings.endpoint, http_timeout=settings.http_timeout)
