from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import TypedDict, Unpack

from acodex.asyncio.tools.base import BaseAsyncTool, RendererToolOutput


class SetThreadArchivedToolInput(TypedDict):
    thread_id: Annotated[str, Field(serialization_alias="threadId")]
    archived: bool


class SetThreadArchivedToolOutput(RendererToolOutput):
    thread_id: str = Field(validation_alias="threadId")
    archived: bool


class SetThreadArchivedTool(BaseAsyncTool[SetThreadArchivedToolOutput]):
    NAME: ClassVar[str] = "set_thread_archived"
    INPUT_TYPE: ClassVar[object] = SetThreadArchivedToolInput
    OUTPUT_TYPE: ClassVar[type[SetThreadArchivedToolOutput]] = SetThreadArchivedToolOutput

    async def __call__(
        self,
        **arguments: Unpack[SetThreadArchivedToolInput],
    ) -> SetThreadArchivedToolOutput:
        """Archive or unarchive a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
