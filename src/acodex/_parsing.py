from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn, TypeVar, cast

from acodex.events import (
    ItemCompletedEvent,
    ItemStartedEvent,
    ItemUpdatedEvent,
    ThreadError,
    ThreadErrorEvent,
    ThreadEvent,
    ThreadStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    TurnStartedEvent,
    Usage,
)
from acodex.items import (
    AgentMessageItem,
    CommandExecutionItem,
    CommandExecutionStatus,
    ErrorItem,
    FileChangeItem,
    FileUpdateChange,
    McpToolCallError,
    McpToolCallItem,
    McpToolCallResult,
    McpToolCallStatus,
    PatchApplyStatus,
    PatchChangeKind,
    ReasoningItem,
    ThreadItem,
    TodoItem,
    TodoListItem,
    WebSearchItem,
)

_ChoiceT = TypeVar("_ChoiceT", bound=str)

COMMAND_EXECUTION_STATUSES: set[CommandExecutionStatus] = {"in_progress", "completed", "failed"}
PATCH_CHANGE_KINDS: set[PatchChangeKind] = {"add", "delete", "update"}
PATCH_APPLY_STATUSES: set[PatchApplyStatus] = {"completed", "failed"}
MCP_TOOL_CALL_STATUSES: set[McpToolCallStatus] = {"in_progress", "completed", "failed"}


def parse_thread_event(raw: object) -> ThreadEvent:
    event = _expect_dict(raw, "event")
    event_type = _expect_str(event.get("type"), "event.type")
    parser = _EVENT_PARSERS.get(event_type)
    if parser is None:
        _raise_value_error(f"Unknown thread event type: {event_type!r}")
    return parser(event)


def parse_thread_item(raw: object) -> ThreadItem:
    item = _expect_dict(raw, "item")
    item_type = _expect_str(item.get("type"), "item.type")
    parser = _ITEM_PARSERS.get(item_type)
    if parser is None:
        _raise_value_error(f"Unknown thread item type: {item_type!r}")
    return parser(item)


def _parse_event_thread_started(event: dict[str, object]) -> ThreadEvent:
    thread_id = _expect_str(event.get("thread_id"), "event.thread_id")
    return ThreadStartedEvent(thread_id=thread_id)


def _parse_event_turn_started(_event: dict[str, object]) -> ThreadEvent:
    return TurnStartedEvent()


def _parse_event_turn_completed(event: dict[str, object]) -> ThreadEvent:
    usage_raw = _expect_dict(event.get("usage"), "event.usage")
    usage = Usage(
        input_tokens=_expect_int(usage_raw.get("input_tokens"), "event.usage.input_tokens"),
        cached_input_tokens=_expect_int(
            usage_raw.get("cached_input_tokens"),
            "event.usage.cached_input_tokens",
        ),
        output_tokens=_expect_int(usage_raw.get("output_tokens"), "event.usage.output_tokens"),
    )
    return TurnCompletedEvent(usage=usage)


def _parse_event_turn_failed(event: dict[str, object]) -> ThreadEvent:
    error_raw = _expect_dict(event.get("error"), "event.error")
    message = _expect_str(error_raw.get("message"), "event.error.message")
    return TurnFailedEvent(error=ThreadError(message=message))


def _parse_event_item_started(event: dict[str, object]) -> ThreadEvent:
    item = parse_thread_item(event.get("item"))
    return ItemStartedEvent(item=item)


def _parse_event_item_updated(event: dict[str, object]) -> ThreadEvent:
    item = parse_thread_item(event.get("item"))
    return ItemUpdatedEvent(item=item)


def _parse_event_item_completed(event: dict[str, object]) -> ThreadEvent:
    item = parse_thread_item(event.get("item"))
    return ItemCompletedEvent(item=item)


def _parse_event_error(event: dict[str, object]) -> ThreadEvent:
    message = _expect_str(event.get("message"), "event.message")
    return ThreadErrorEvent(message=message)


_EVENT_PARSERS: dict[str, Callable[[dict[str, object]], ThreadEvent]] = {
    "thread.started": _parse_event_thread_started,
    "turn.started": _parse_event_turn_started,
    "turn.completed": _parse_event_turn_completed,
    "turn.failed": _parse_event_turn_failed,
    "item.started": _parse_event_item_started,
    "item.updated": _parse_event_item_updated,
    "item.completed": _parse_event_item_completed,
    "error": _parse_event_error,
}


def _parse_item_agent_message(item: dict[str, object]) -> ThreadItem:
    return AgentMessageItem(
        id=_expect_str(item.get("id"), "item.id"),
        text=_expect_str(item.get("text"), "item.text"),
    )


def _parse_item_reasoning(item: dict[str, object]) -> ThreadItem:
    return ReasoningItem(
        id=_expect_str(item.get("id"), "item.id"),
        text=_expect_str(item.get("text"), "item.text"),
    )


def _parse_item_command_execution(item: dict[str, object]) -> ThreadItem:
    exit_code = item.get("exit_code")
    parsed_exit_code = None if exit_code is None else _expect_int(exit_code, "item.exit_code")
    return CommandExecutionItem(
        id=_expect_str(item.get("id"), "item.id"),
        command=_expect_str(item.get("command"), "item.command"),
        aggregated_output=_expect_str(item.get("aggregated_output"), "item.aggregated_output"),
        status=_expect_str_choice(
            item.get("status"),
            "item.status",
            COMMAND_EXECUTION_STATUSES,
        ),
        exit_code=parsed_exit_code,
    )


def _parse_item_file_change(item: dict[str, object]) -> ThreadItem:
    changes_raw = _expect_list(item.get("changes"), "item.changes")
    changes: list[FileUpdateChange] = []
    for index, change_raw in enumerate(changes_raw):
        change_path = f"item.changes[{index}]"
        change = _expect_dict(change_raw, change_path)
        kind = _expect_str_choice(
            change.get("kind"),
            f"{change_path}.kind",
            PATCH_CHANGE_KINDS,
        )
        changes.append(
            FileUpdateChange(
                path=_expect_str(change.get("path"), f"{change_path}.path"),
                kind=kind,
            ),
        )
    return FileChangeItem(
        id=_expect_str(item.get("id"), "item.id"),
        changes=changes,
        status=_expect_str_choice(item.get("status"), "item.status", PATCH_APPLY_STATUSES),
    )


def _parse_item_mcp_tool_call(item: dict[str, object]) -> ThreadItem:
    result_raw = item.get("result")
    parsed_result: McpToolCallResult | None
    if result_raw is None:
        parsed_result = None
    else:
        result = _expect_dict(result_raw, "item.result")
        content = _expect_list(result.get("content"), "item.result.content")
        if "structured_content" not in result:
            _raise_value_error("Missing key item.result.structured_content")
        structured_content = result.get("structured_content")
        parsed_result = McpToolCallResult(content=content, structured_content=structured_content)

    error_raw = item.get("error")
    parsed_error: McpToolCallError | None
    if error_raw is None:
        parsed_error = None
    else:
        error = _expect_dict(error_raw, "item.error")
        parsed_error = McpToolCallError(
            message=_expect_str(error.get("message"), "item.error.message")
        )

    return McpToolCallItem(
        id=_expect_str(item.get("id"), "item.id"),
        server=_expect_str(item.get("server"), "item.server"),
        tool=_expect_str(item.get("tool"), "item.tool"),
        arguments=item.get("arguments"),
        status=_expect_str_choice(
            item.get("status"),
            "item.status",
            MCP_TOOL_CALL_STATUSES,
        ),
        result=parsed_result,
        error=parsed_error,
    )


def _parse_item_web_search(item: dict[str, object]) -> ThreadItem:
    return WebSearchItem(
        id=_expect_str(item.get("id"), "item.id"),
        query=_expect_str(item.get("query"), "item.query"),
    )


def _parse_item_todo_list(item: dict[str, object]) -> ThreadItem:
    items_raw = _expect_list(item.get("items"), "item.items")
    todo_items: list[TodoItem] = []
    for index, todo_raw in enumerate(items_raw):
        todo_path = f"item.items[{index}]"
        todo = _expect_dict(todo_raw, todo_path)
        todo_items.append(
            TodoItem(
                text=_expect_str(todo.get("text"), f"{todo_path}.text"),
                completed=_expect_bool(todo.get("completed"), f"{todo_path}.completed"),
            ),
        )
    return TodoListItem(id=_expect_str(item.get("id"), "item.id"), items=todo_items)


def _parse_item_error(item: dict[str, object]) -> ThreadItem:
    return ErrorItem(
        id=_expect_str(item.get("id"), "item.id"),
        message=_expect_str(item.get("message"), "item.message"),
    )


_ITEM_PARSERS: dict[str, Callable[[dict[str, object]], ThreadItem]] = {
    "agent_message": _parse_item_agent_message,
    "reasoning": _parse_item_reasoning,
    "command_execution": _parse_item_command_execution,
    "file_change": _parse_item_file_change,
    "mcp_tool_call": _parse_item_mcp_tool_call,
    "web_search": _parse_item_web_search,
    "todo_list": _parse_item_todo_list,
    "error": _parse_item_error,
}


def _expect_dict(value: object, path: str) -> dict[str, object]:
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                _raise_value_error(f"{path} keys must be strings")
        return cast("dict[str, object]", value)
    _raise_value_error(f"{path} must be an object")
    raise AssertionError


def _expect_list(value: object, path: str) -> list[object]:
    if isinstance(value, list):
        return value
    _raise_value_error(f"{path} must be an array")
    raise AssertionError


def _expect_str(value: object, path: str) -> str:
    if isinstance(value, str):
        return value
    _raise_value_error(f"{path} must be a string")
    raise AssertionError


def _expect_bool(value: object, path: str) -> bool:
    if isinstance(value, bool):
        return value
    _raise_value_error(f"{path} must be a boolean")
    raise AssertionError


def _expect_int(value: object, path: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    _raise_value_error(f"{path} must be an integer")
    raise AssertionError


def _expect_str_choice(value: object, path: str, choices: set[_ChoiceT]) -> _ChoiceT:
    rendered = _expect_str(value, path)
    for choice in choices:
        if rendered == choice:
            return choice
    allowed = ", ".join(sorted(choices))
    _raise_value_error(f"{path} must be one of: {allowed}")
    raise AssertionError


def _raise_value_error(message: str) -> NoReturn:
    raise ValueError(message)
