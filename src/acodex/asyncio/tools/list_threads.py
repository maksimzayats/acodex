from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field
from typing_extensions import NotRequired, TypedDict, Unpack

from acodex.asyncio.tools.base import BaseAsyncTool, RendererToolOutput


class ListThreadsToolInput(TypedDict):
    limit: NotRequired[int | None]
    query: NotRequired[str | None]


class ListThreadsThread(RendererToolOutput):
    id: str
    title: str
    preview: str
    status: str
    cwd: str | None
    created_at: int | float = Field(validation_alias="createdAt")
    updated_at: int | float = Field(validation_alias="updatedAt")


class ListThreadsToolOutput(RendererToolOutput):
    schema_version: Literal[1] = Field(validation_alias="schemaVersion")
    query: str | None
    threads: list[ListThreadsThread]


class ListThreadsTool(BaseAsyncTool[ListThreadsToolOutput]):
    NAME: ClassVar[str] = "list_threads"
    INPUT_TYPE: ClassVar[object] = ListThreadsToolInput
    OUTPUT_TYPE: ClassVar[type[ListThreadsToolOutput]] = ListThreadsToolOutput

    async def __call__(self, **arguments: Unpack[ListThreadsToolInput]) -> ListThreadsToolOutput:
        """List recent Codex desktop threads.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
