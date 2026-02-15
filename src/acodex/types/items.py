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
    """Stable identifier for this thread item."""

    command: str
    """Command line executed by the agent."""

    aggregated_output: str
    """Aggregated stdout and stderr captured while the command was running."""

    status: CommandExecutionStatus
    """Current status of the command execution."""

    exit_code: int | None = None
    """Exit code once the command exits; ``None`` while still running."""

    type: Literal["command_execution"] = field(default="command_execution", init=False)
    """Discriminator with value ``"command_execution"``."""


@dataclass(frozen=True, slots=True)
class FileUpdateChange:
    """A file update included in a patch operation."""

    path: str
    """Path to the changed file."""

    kind: PatchChangeKind
    """Kind of patch change (add, delete, or update)."""


@dataclass(frozen=True, slots=True)
class FileChangeItem:
    """A set of file changes by the agent.

    Emitted once the patch succeeds or fails.

    """

    id: str
    """Stable identifier for this thread item."""

    changes: list[FileUpdateChange]
    """Individual file changes that comprise the patch."""

    status: PatchApplyStatus
    """Whether the patch ultimately succeeded or failed."""

    type: Literal["file_change"] = field(default="file_change", init=False)
    """Discriminator with value ``"file_change"``."""


@dataclass(frozen=True, slots=True)
class McpToolCallResult:
    """Result payload returned by an MCP server."""

    content: list[object]
    """MCP content blocks returned for successful calls."""

    structured_content: object
    """Structured payload returned by the MCP server."""


@dataclass(frozen=True, slots=True)
class McpToolCallError:
    """Error payload returned for a failed MCP call."""

    message: str
    """Error message reported by the MCP server."""


@dataclass(frozen=True, slots=True)
class McpToolCallItem:
    """Represents a call to an MCP tool.

    The item starts when invocation is dispatched and completes when the MCP server reports
    success or failure.

    """

    id: str
    """Stable identifier for this thread item."""

    server: str
    """Name of the MCP server handling the request."""

    tool: str
    """Tool invoked on the MCP server."""

    arguments: object
    """Arguments forwarded to the tool invocation."""

    status: McpToolCallStatus
    """Current status of the tool invocation."""

    result: McpToolCallResult | None = None
    """Result payload for successful calls; ``None`` when not available."""

    error: McpToolCallError | None = None
    """Error payload for failed calls; ``None`` when not available."""

    type: Literal["mcp_tool_call"] = field(default="mcp_tool_call", init=False)
    """Discriminator with value ``"mcp_tool_call"``."""


@dataclass(frozen=True, slots=True)
class AgentMessageItem:
    """Response from the agent.

    The text can be natural language or JSON when structured output is requested.

    """

    id: str
    """Stable identifier for this thread item."""

    text: str
    """Agent response payload."""

    type: Literal["agent_message"] = field(default="agent_message", init=False)
    """Discriminator with value ``"agent_message"``."""


@dataclass(frozen=True, slots=True)
class ReasoningItem:
    """Agent reasoning summary."""

    id: str
    """Stable identifier for this thread item."""

    text: str
    """Reasoning summary text."""

    type: Literal["reasoning"] = field(default="reasoning", init=False)
    """Discriminator with value ``"reasoning"``."""


@dataclass(frozen=True, slots=True)
class WebSearchItem:
    """Captures a web search request.

    The item completes when results are returned to the agent.

    """

    id: str
    """Stable identifier for this thread item."""

    query: str
    """Search query text."""

    type: Literal["web_search"] = field(default="web_search", init=False)
    """Discriminator with value ``"web_search"``."""


@dataclass(frozen=True, slots=True)
class ErrorItem:
    """Describes a non-fatal error surfaced as an item."""

    id: str
    """Stable identifier for this thread item."""

    message: str
    """Error message."""

    type: Literal["error"] = field(default="error", init=False)
    """Discriminator with value ``"error"``."""


@dataclass(frozen=True, slots=True)
class TodoItem:
    """An item in the agent to-do list."""

    text: str
    """To-do item text."""

    completed: bool
    """Whether the item is completed."""


@dataclass(frozen=True, slots=True)
class TodoListItem:
    """Tracks the agent running to-do list.

    Starts when a plan is issued, updates as steps change, and completes when the turn ends.

    """

    id: str
    """Stable identifier for this thread item."""

    items: list[TodoItem]
    """Current to-do list items."""

    type: Literal["todo_list"] = field(default="todo_list", init=False)
    """Discriminator with value ``"todo_list"``."""


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
