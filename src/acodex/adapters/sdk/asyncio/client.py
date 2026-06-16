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

class AsyncCodexApp:
    def __init__(
        self,
        settings: CodexAppCdpSettings | None = None,
    ) -> None:
        self._settings = settings or CodexAppCdpSettings()

    async def __aenter__(self) -> Self:
        return await self.connect()

    async def __aexit__(  # noqa: PLR0917
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def connect(self) -> Self:
        pass

    async def close(self) -> None:
        pass

    # region: Thread Tools

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

    # endregion: Thread Tools
