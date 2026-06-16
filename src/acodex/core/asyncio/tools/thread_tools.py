from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Self

from acodex.core.asyncio.tools.base import AsyncRendererToolInvoker
from acodex.core.asyncio.tools.create_thread import CreateThreadTool
from acodex.core.asyncio.tools.fork_thread import ForkThreadTool
from acodex.core.asyncio.tools.handoff_thread import HandoffThreadTool
from acodex.core.asyncio.tools.list_threads import ListThreadsTool
from acodex.core.asyncio.tools.read_thread import ReadThreadTool
from acodex.core.asyncio.tools.send_message_to_thread import SendMessageToThreadTool
from acodex.core.asyncio.tools.set_thread_archived import SetThreadArchivedTool
from acodex.core.asyncio.tools.set_thread_pinned import SetThreadPinnedTool
from acodex.core.asyncio.tools.set_thread_title import SetThreadTitleTool


@dataclass(frozen=True, slots=True)
class CodexAppThreadTools:
    list_threads: ListThreadsTool
    read_thread: ReadThreadTool
    create_thread: CreateThreadTool
    send_message_to_thread: SendMessageToThreadTool
    fork_thread: ForkThreadTool
    set_thread_pinned: SetThreadPinnedTool
    set_thread_archived: SetThreadArchivedTool
    set_thread_title: SetThreadTitleTool
    handoff_thread: HandoffThreadTool

    @classmethod
    def bind(cls, invoker: AsyncRendererToolInvoker) -> Self:
        """Bind every Codex app thread tool to one renderer invoker.

        Returns:
            A grouped set of bound tool instances.

        """
        return cls(
            list_threads=ListThreadsTool(invoker),
            read_thread=ReadThreadTool(invoker),
            create_thread=CreateThreadTool(invoker),
            send_message_to_thread=SendMessageToThreadTool(invoker),
            fork_thread=ForkThreadTool(invoker),
            set_thread_pinned=SetThreadPinnedTool(invoker),
            set_thread_archived=SetThreadArchivedTool(invoker),
            set_thread_title=SetThreadTitleTool(invoker),
            handoff_thread=HandoffThreadTool(invoker),
        )
