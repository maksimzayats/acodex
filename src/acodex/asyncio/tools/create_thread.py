from __future__ import annotations

from typing import Annotated, Any, ClassVar, TypeAlias

from pydantic import Field, model_validator
from typing_extensions import NotRequired, TypedDict, Unpack

from acodex.asyncio.cdp.types import ThinkingEffort
from acodex.asyncio.tools.base import BaseAsyncTool, RendererToolOutput

# Target schemas are open-ended renderer payloads; JSON validation happens after dump.
RendererJsonObject: TypeAlias = dict[str, Any]


class CreateThreadToolInput(TypedDict):
    prompt: str
    target: Annotated[RendererJsonObject, Field(serialization_alias="target")]
    model: NotRequired[str | None]
    thinking: NotRequired[ThinkingEffort | None]


class CreateThreadToolOutput(RendererToolOutput):
    thread_id: str | None = Field(default=None, validation_alias="threadId")
    pending_worktree_id: str | None = Field(default=None, validation_alias="pendingWorktreeId")
    projectless_output_directory: str | None = Field(
        default=None,
        validation_alias="projectlessOutputDirectory",
    )

    @model_validator(mode="after")
    def _validate_created_or_pending(self) -> CreateThreadToolOutput:
        if self.thread_id is None and self.pending_worktree_id is None:
            raise ValueError("create_thread output must include threadId or pendingWorktreeId")
        return self


class CreateThreadTool(BaseAsyncTool[CreateThreadToolOutput]):
    NAME: ClassVar[str] = "create_thread"
    INPUT_TYPE: ClassVar[object] = CreateThreadToolInput
    OUTPUT_TYPE: ClassVar[type[CreateThreadToolOutput]] = CreateThreadToolOutput

    async def __call__(
        self,
        **arguments: Unpack[CreateThreadToolInput],
    ) -> CreateThreadToolOutput:
        """Create a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
