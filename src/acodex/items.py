from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

CommandExecutionStatus: TypeAlias = Literal["in_progress", "completed", "failed"]
PatchChangeKind: TypeAlias = Literal["add", "delete", "update"]
PatchApplyStatus: TypeAlias = Literal["completed", "failed"]
McpToolCallStatus: TypeAlias = Literal["in_progress", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class CommandExecutionItem:
    """A command executed by the agent."""

    id: str
    command: str
    aggregated_output: str
    status: CommandExecutionStatus
    exit_code: int | None = None
    type: Literal["command_execution"] = field(default="command_execution", init=False)


@dataclass(frozen=True, slots=True)
class FileUpdateChange:
    """A file update included in a patch operation."""

    path: str
    kind: PatchChangeKind


@dataclass(frozen=True, slots=True)
class FileChangeItem:
    """A set of file changes by the agent."""

    id: str
    changes: list[FileUpdateChange]
    status: PatchApplyStatus
    type: Literal["file_change"] = field(default="file_change", init=False)


@dataclass(frozen=True, slots=True)
class McpToolCallResult:
    """Result payload returned by an MCP server."""

    content: list[object]
    structured_content: object


@dataclass(frozen=True, slots=True)
class McpToolCallError:
    """Error payload returned for a failed MCP call."""

    message: str


@dataclass(frozen=True, slots=True)
class McpToolCallItem:
    """Represents a call to an MCP tool."""

    id: str
    server: str
    tool: str
    arguments: object
    status: McpToolCallStatus
    result: McpToolCallResult | None = None
    error: McpToolCallError | None = None
    type: Literal["mcp_tool_call"] = field(default="mcp_tool_call", init=False)


@dataclass(frozen=True, slots=True)
class AgentMessageItem:
    """Response from the agent."""

    id: str
    text: str
    type: Literal["agent_message"] = field(default="agent_message", init=False)


@dataclass(frozen=True, slots=True)
class ReasoningItem:
    """Agent's reasoning summary."""

    id: str
    text: str
    type: Literal["reasoning"] = field(default="reasoning", init=False)


@dataclass(frozen=True, slots=True)
class WebSearchItem:
    """Captures a web search request."""

    id: str
    query: str
    type: Literal["web_search"] = field(default="web_search", init=False)


@dataclass(frozen=True, slots=True)
class ErrorItem:
    """Describes a non-fatal error surfaced as an item."""

    id: str
    message: str
    type: Literal["error"] = field(default="error", init=False)


@dataclass(frozen=True, slots=True)
class TodoItem:
    """An item in the agent's to-do list."""

    text: str
    completed: bool


@dataclass(frozen=True, slots=True)
class TodoListItem:
    """Tracks the agent's running to-do list."""

    id: str
    items: list[TodoItem]
    type: Literal["todo_list"] = field(default="todo_list", init=False)


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
