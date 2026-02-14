from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired

CommandExecutionStatus: TypeAlias = Literal["in_progress", "completed", "failed"]
PatchChangeKind: TypeAlias = Literal["add", "delete", "update"]
PatchApplyStatus: TypeAlias = Literal["completed", "failed"]
McpToolCallStatus: TypeAlias = Literal["in_progress", "completed", "failed"]


class CommandExecutionItem(TypedDict):
    """A command executed by the agent."""

    id: str
    type: Literal["command_execution"]
    command: str
    aggregated_output: str
    exit_code: NotRequired[int]
    status: CommandExecutionStatus


class FileUpdateChange(TypedDict):
    """A file update included in a patch operation."""

    path: str
    kind: PatchChangeKind


class FileChangeItem(TypedDict):
    """A set of file changes by the agent."""

    id: str
    type: Literal["file_change"]
    changes: list[FileUpdateChange]
    status: PatchApplyStatus


class McpToolCallResult(TypedDict):
    """Result payload returned by an MCP server."""

    content: list[object]
    structured_content: object


class McpToolCallError(TypedDict):
    """Error payload returned for a failed MCP call."""

    message: str


class McpToolCallItem(TypedDict):
    """Represents a call to an MCP tool."""

    id: str
    type: Literal["mcp_tool_call"]
    server: str
    tool: str
    arguments: object
    result: NotRequired[McpToolCallResult]
    error: NotRequired[McpToolCallError]
    status: McpToolCallStatus


class AgentMessageItem(TypedDict):
    """Response from the agent."""

    id: str
    type: Literal["agent_message"]
    text: str


class ReasoningItem(TypedDict):
    """Agent's reasoning summary."""

    id: str
    type: Literal["reasoning"]
    text: str


class WebSearchItem(TypedDict):
    """Captures a web search request."""

    id: str
    type: Literal["web_search"]
    query: str


class ErrorItem(TypedDict):
    """Describes a non-fatal error surfaced as an item."""

    id: str
    type: Literal["error"]
    message: str


class TodoItem(TypedDict):
    """An item in the agent's to-do list."""

    text: str
    completed: bool


class TodoListItem(TypedDict):
    """Tracks the agent's running to-do list."""

    id: str
    type: Literal["todo_list"]
    items: list[TodoItem]


ThreadItem: TypeAlias = (
    AgentMessageItem
    | ReasoningItem
    | CommandExecutionItem
    | FileChangeItem
    | McpToolCallItem
    | WebSearchItem
    | TodoListItem
    | ErrorItem
)
