from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal, TypeAlias

from pydantic import Field
from typing_extensions import NotRequired, TypedDict, Unpack

from acodex.core.asyncio.cdp.types import ThinkingEffort
from acodex.core.asyncio.tools.base import BaseAsyncTool, RendererToolOutput

# Some read_thread item fields contain arbitrary renderer JSON; envelope validation handles JSON.
ReadThreadJsonValue: TypeAlias = Any


class ReadThreadToolInput(TypedDict):
    thread_id: Annotated[str, Field(serialization_alias="threadId")]
    cursor: NotRequired[str | None]
    include_outputs: NotRequired[
        Annotated[bool | None, Field(serialization_alias="includeOutputs")]
    ]
    max_output_chars_per_item: NotRequired[
        Annotated[int | None, Field(serialization_alias="maxOutputCharsPerItem")]
    ]
    turn_limit: NotRequired[Annotated[int | None, Field(serialization_alias="turnLimit")]]


class ReadThreadActiveStatus(RendererToolOutput):
    type: Literal["active"]
    active_flags: list[str] = Field(validation_alias="activeFlags")


class ReadThreadSimpleStatus(RendererToolOutput):
    type: Literal["idle", "notLoaded", "systemError"]


ReadThreadStatus: TypeAlias = Annotated[
    ReadThreadActiveStatus | ReadThreadSimpleStatus,
    Field(discriminator="type"),
]


class ReadThreadThread(RendererToolOutput):
    id: str
    title: str
    preview: str
    status: ReadThreadStatus
    cwd: str | None
    created_at: int | float = Field(validation_alias="createdAt")
    updated_at: int | float = Field(validation_alias="updatedAt")


class ReadThreadPage(RendererToolOutput):
    order: Literal["newest_first"]
    limit: int
    next_cursor: str | None = Field(validation_alias="nextCursor")
    has_more: bool = Field(validation_alias="hasMore")


class ReadThreadTruncatedText(RendererToolOutput):
    text: str
    truncated: bool
    original_chars: int | None = Field(default=None, validation_alias="originalChars")


class ReadThreadTurnError(RendererToolOutput):
    message: str
    additional_details: str | None = Field(default=None, validation_alias="additionalDetails")


class ReadThreadDelegation(RendererToolOutput):
    source_thread_id: str = Field(validation_alias="sourceThreadId")
    input: str


class ReadThreadTextContent(RendererToolOutput):
    type: Literal["text"]
    text: str
    codex_delegation: ReadThreadDelegation | None = Field(
        default=None,
        validation_alias="codexDelegation",
    )


class ReadThreadImageContent(RendererToolOutput):
    type: Literal["image"]
    url: str


class ReadThreadLocalImageContent(RendererToolOutput):
    type: Literal["localImage"]
    path: str


class ReadThreadNamedPathContent(RendererToolOutput):
    type: Literal["skill", "mention"]
    name: str
    path: str


ReadThreadContent: TypeAlias = Annotated[
    ReadThreadTextContent
    | ReadThreadImageContent
    | ReadThreadLocalImageContent
    | ReadThreadNamedPathContent,
    Field(discriminator="type"),
]


class ReadThreadUserMessageItem(RendererToolOutput):
    type: Literal["userMessage"]
    id: str
    content: list[ReadThreadContent]


class ReadThreadAgentMessageItem(RendererToolOutput):
    type: Literal["agentMessage"]
    id: str
    text: str
    phase: str


class ReadThreadPlanItem(RendererToolOutput):
    type: Literal["plan"]
    id: str
    text: str


class ReadThreadReasoningItem(RendererToolOutput):
    type: Literal["reasoning"]
    id: str
    summary: str
    content: list[ReadThreadTruncatedText] | None = None


class ReadThreadCommandExecutionItem(RendererToolOutput):
    type: Literal["commandExecution"]
    id: str
    command: str
    cwd: str | None = None
    status: str
    exit_code: int | None = Field(default=None, validation_alias="exitCode")
    duration_ms: int | float | None = Field(default=None, validation_alias="durationMs")
    output: ReadThreadTruncatedText | None = None


class ReadThreadFileChangeAddKind(RendererToolOutput):
    type: Literal["add"]


class ReadThreadFileChangeUpdateKind(RendererToolOutput):
    type: Literal["update"]
    move_path: str | None = Field(default=None, validation_alias="move_path")


class ReadThreadFileChangeDeleteKind(RendererToolOutput):
    type: Literal["delete"]


ReadThreadFileChangeKind: TypeAlias = Annotated[
    ReadThreadFileChangeAddKind | ReadThreadFileChangeUpdateKind | ReadThreadFileChangeDeleteKind,
    Field(discriminator="type"),
]


class ReadThreadFileChange(RendererToolOutput):
    path: str
    kind: ReadThreadFileChangeKind
    diff: ReadThreadTruncatedText | None = None


class ReadThreadFileChangeItem(RendererToolOutput):
    type: Literal["fileChange"]
    id: str
    status: str
    changes: list[ReadThreadFileChange]


class ReadThreadMcpToolCallItem(RendererToolOutput):
    type: Literal["mcpToolCall"]
    id: str
    server: str
    tool: str
    arguments: ReadThreadJsonValue
    status: str
    duration_ms: int | float | None = Field(default=None, validation_alias="durationMs")


class ReadThreadDynamicToolCallItem(RendererToolOutput):
    type: Literal["dynamicToolCall"]
    id: str
    tool: str
    arguments: ReadThreadJsonValue
    status: str
    success: bool | None = None
    duration_ms: int | float | None = Field(default=None, validation_alias="durationMs")


class ReadThreadCollabAgentToolCallItem(RendererToolOutput):
    type: Literal["collabAgentToolCall"]
    id: str
    tool: str
    status: str
    sender_thread_id: str = Field(validation_alias="senderThreadId")
    receiver_thread_ids: list[str] = Field(validation_alias="receiverThreadIds")
    prompt: str
    model: str | None = None
    reasoning_effort: ThinkingEffort | None = Field(
        default=None,
        validation_alias="reasoningEffort",
    )


class ReadThreadSubAgentActivityItem(RendererToolOutput):
    type: Literal["subAgentActivity"]
    id: str
    kind: str
    agent_thread_id: str = Field(validation_alias="agentThreadId")
    agent_path: str | None = Field(default=None, validation_alias="agentPath")


class ReadThreadWebSearchItem(RendererToolOutput):
    type: Literal["webSearch"]
    id: str
    query: str
    action: str


class ReadThreadImageViewItem(RendererToolOutput):
    type: Literal["imageView"]
    id: str
    path: str


class ReadThreadImageGenerationItem(RendererToolOutput):
    type: Literal["imageGeneration"]
    id: str
    status: str
    revised_prompt: str | None = Field(default=None, validation_alias="revisedPrompt")
    result: ReadThreadJsonValue = None
    saved_path: str | None = Field(validation_alias="savedPath")


class ReadThreadReviewModeItem(RendererToolOutput):
    type: Literal["enteredReviewMode", "exitedReviewMode"]
    id: str
    review: ReadThreadJsonValue


class ReadThreadHookPromptItem(RendererToolOutput):
    type: Literal["hookPrompt"]
    id: str
    fragment_count: int = Field(validation_alias="fragmentCount")


class ReadThreadContextCompactionItem(RendererToolOutput):
    type: Literal["contextCompaction"]
    id: str


ReadThreadItem: TypeAlias = Annotated[
    ReadThreadUserMessageItem
    | ReadThreadAgentMessageItem
    | ReadThreadPlanItem
    | ReadThreadReasoningItem
    | ReadThreadCommandExecutionItem
    | ReadThreadFileChangeItem
    | ReadThreadMcpToolCallItem
    | ReadThreadDynamicToolCallItem
    | ReadThreadCollabAgentToolCallItem
    | ReadThreadSubAgentActivityItem
    | ReadThreadWebSearchItem
    | ReadThreadImageViewItem
    | ReadThreadImageGenerationItem
    | ReadThreadReviewModeItem
    | ReadThreadHookPromptItem
    | ReadThreadContextCompactionItem,
    Field(discriminator="type"),
]


class ReadThreadTurn(RendererToolOutput):
    id: str
    status: str
    error: ReadThreadTurnError | None
    started_at: int | float | None = Field(default=None, validation_alias="startedAt")
    completed_at: int | float | None = Field(default=None, validation_alias="completedAt")
    duration_ms: int | float | None = Field(default=None, validation_alias="durationMs")
    items: list[ReadThreadItem]


class ReadThreadToolOutput(RendererToolOutput):
    schema_version: Literal[1] = Field(validation_alias="schemaVersion")
    thread: ReadThreadThread
    page: ReadThreadPage
    turns: list[ReadThreadTurn]


class ReadThreadTool(BaseAsyncTool[ReadThreadToolOutput]):
    NAME: ClassVar[str] = "read_thread"
    INPUT_TYPE: ClassVar[object] = ReadThreadToolInput
    OUTPUT_TYPE: ClassVar[type[ReadThreadToolOutput]] = ReadThreadToolOutput

    async def __call__(self, **arguments: Unpack[ReadThreadToolInput]) -> ReadThreadToolOutput:
        """Read recent metadata and turns for one Codex desktop thread.

        Returns:
            A typed output model wrapping the renderer-native result.

        """
        return await self._invoke(arguments)
