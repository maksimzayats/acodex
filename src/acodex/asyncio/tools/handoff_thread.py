from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import NotRequired, TypedDict, Unpack

from acodex.asyncio.tools.base import BaseAsyncTool, RendererToolOutput


class HandoffThreadToolInput(TypedDict):
    thread_id: Annotated[str, Field(serialization_alias="threadId")]
    destination_host_id: NotRequired[
        Annotated[str | None, Field(serialization_alias="destinationHostId")]
    ]


class HandoffThreadToolOutput(RendererToolOutput):
    destination_host_display_name: str = Field(validation_alias="destinationHostDisplayName")
    thread_id: str = Field(validation_alias="threadId")
    thread_title: str = Field(validation_alias="threadTitle")


class HandoffThreadTool(BaseAsyncTool[HandoffThreadToolOutput]):
    NAME: ClassVar[str] = "handoff_thread"
    INPUT_TYPE: ClassVar[object] = HandoffThreadToolInput
    OUTPUT_TYPE: ClassVar[type[HandoffThreadToolOutput]] = HandoffThreadToolOutput

    async def __call__(
        self,
        **arguments: Unpack[HandoffThreadToolInput],
    ) -> HandoffThreadToolOutput:
        """Hand off a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
