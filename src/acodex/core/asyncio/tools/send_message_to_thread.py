from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import NotRequired, TypedDict, Unpack

from acodex.core.asyncio.cdp.types import ThinkingEffort
from acodex.core.asyncio.tools.base import BaseAsyncTool, RendererToolOutput


class SendMessageToThreadToolInput(TypedDict):
    thread_id: Annotated[str, Field(serialization_alias="threadId")]
    prompt: str
    model: NotRequired[str | None]
    thinking: NotRequired[ThinkingEffort | None]


class SendMessageToThreadToolOutput(RendererToolOutput):
    thread_id: str = Field(validation_alias="threadId")


class SendMessageToThreadTool(BaseAsyncTool[SendMessageToThreadToolOutput]):
    NAME: ClassVar[str] = "send_message_to_thread"
    INPUT_TYPE: ClassVar[object] = SendMessageToThreadToolInput
    OUTPUT_TYPE: ClassVar[type[SendMessageToThreadToolOutput]] = SendMessageToThreadToolOutput

    async def __call__(
        self,
        **arguments: Unpack[SendMessageToThreadToolInput],
    ) -> SendMessageToThreadToolOutput:
        """Send a prompt to an existing Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
