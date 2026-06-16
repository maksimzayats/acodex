from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import TypedDict, Unpack

from acodex.core.asyncio.tools.base import BaseAsyncTool, RendererToolOutput


class SetThreadTitleToolInput(TypedDict):
    thread_id: Annotated[str, Field(serialization_alias="threadId")]
    title: str


class SetThreadTitleToolOutput(RendererToolOutput):
    thread_id: str = Field(validation_alias="threadId")
    title: str


class SetThreadTitleTool(BaseAsyncTool[SetThreadTitleToolOutput]):
    NAME: ClassVar[str] = "set_thread_title"
    INPUT_TYPE: ClassVar[object] = SetThreadTitleToolInput
    OUTPUT_TYPE: ClassVar[type[SetThreadTitleToolOutput]] = SetThreadTitleToolOutput

    async def __call__(
        self,
        **arguments: Unpack[SetThreadTitleToolInput],
    ) -> SetThreadTitleToolOutput:
        """Rename a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
