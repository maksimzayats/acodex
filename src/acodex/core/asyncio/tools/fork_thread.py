from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, TypeAlias

from pydantic import Field, model_validator
from typing_extensions import NotRequired, TypedDict, Unpack

from acodex.core.asyncio.tools.base import BaseAsyncTool, RendererToolOutput

# Environment schemas are open-ended renderer payloads; JSON validation happens after dump.
RendererJsonObject: TypeAlias = dict[str, Any]


class ForkThreadToolInput(TypedDict):
    thread_id: NotRequired[Annotated[str | None, Field(serialization_alias="threadId")]]
    environment: NotRequired[RendererJsonObject | None]


class ForkThreadOutputSameDirectoryEnvironment(RendererToolOutput):
    type: Literal["same-directory"]


class ForkThreadOutputWorktreeEnvironment(RendererToolOutput):
    type: Literal["worktree"]


ForkThreadOutputEnvironment: TypeAlias = Annotated[
    ForkThreadOutputSameDirectoryEnvironment | ForkThreadOutputWorktreeEnvironment,
    Field(discriminator="type"),
]


class ForkThreadToolOutput(RendererToolOutput):
    environment: ForkThreadOutputEnvironment
    source_thread_id: str = Field(validation_alias="sourceThreadId")
    thread_id: str | None = Field(default=None, validation_alias="threadId")
    pending_worktree_id: str | None = Field(default=None, validation_alias="pendingWorktreeId")
    continuation: str

    @model_validator(mode="after")
    def _validate_fork_target(self) -> ForkThreadToolOutput:
        if self.thread_id is None and self.pending_worktree_id is None:
            raise ValueError("fork_thread output must include threadId or pendingWorktreeId")
        return self


class ForkThreadTool(BaseAsyncTool[ForkThreadToolOutput]):
    NAME: ClassVar[str] = "fork_thread"
    INPUT_TYPE: ClassVar[object] = ForkThreadToolInput
    OUTPUT_TYPE: ClassVar[type[ForkThreadToolOutput]] = ForkThreadToolOutput

    async def __call__(
        self,
        *,
        source_thread_id: str,
        **arguments: Unpack[ForkThreadToolInput],
    ) -> ForkThreadToolOutput:
        """Fork a Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments, source_thread_id=source_thread_id)
