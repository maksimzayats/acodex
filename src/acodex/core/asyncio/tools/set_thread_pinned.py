from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import TypedDict, Unpack

from acodex.core.asyncio.tools.base import BaseAsyncTool, RendererToolOutput


class SetThreadPinnedToolInput(TypedDict):
    thread_id: Annotated[str, Field(serialization_alias="threadId")]
    pinned: bool


class SetThreadPinnedToolOutput(RendererToolOutput):
    thread_id: str = Field(validation_alias="threadId")
    pinned: bool


class SetThreadPinnedTool(BaseAsyncTool[SetThreadPinnedToolOutput]):
    NAME: ClassVar[str] = "set_thread_pinned"
    INPUT_TYPE: ClassVar[object] = SetThreadPinnedToolInput
    OUTPUT_TYPE: ClassVar[type[SetThreadPinnedToolOutput]] = SetThreadPinnedToolOutput

    async def __call__(
        self,
        **arguments: Unpack[SetThreadPinnedToolInput],
    ) -> SetThreadPinnedToolOutput:
        """Pin or unpin a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
