from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import NamedTuple, TypeVar, cast

from acodex._internal.output_type import OutputTypeAdapter
from acodex.exceptions import CodexStructuredResponseError, CodexThreadRunError
from acodex.types.events import (
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
from acodex.types.input import Input, UserInputLocalImage, UserInputText
from acodex.types.items import (
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
from acodex.types.turn import Turn

T = TypeVar("T")

logger = logging.getLogger(__name__)


class NormalizedInput(NamedTuple):
    prompt: str
    images: list[str]


def normalize_input(input: Input) -> NormalizedInput:  # noqa: A002
    if isinstance(input, str):
        return NormalizedInput(prompt=input, images=[])

    if not isinstance(input, list):
        raise TypeError(f"input must be str or list[UserInput], got {type(input).__name__}")

    prompt_parts: list[str] = []
    images: list[str] = []

    for index, raw_item in enumerate(input):
        if isinstance(raw_item, UserInputText):
            prompt_parts.append(raw_item.text)
            continue

        if isinstance(raw_item, UserInputLocalImage):
            images.append(raw_item.path)
            continue

        raise TypeError(
            f"input[{index}] must be UserInputText or UserInputLocalImage, got {type(raw_item).__name__}",
        )

    return NormalizedInput(prompt="\n\n".join(prompt_parts), images=images)


def parse_thread_event_jsonl(line: str) -> ThreadEvent | None:
    try:
        payload_obj = json.loads(line)
    except json.JSONDecodeError as error:
        raise CodexThreadRunError(f"Failed to parse item: {line}") from error

    if not isinstance(payload_obj, dict):
        raise CodexThreadRunError(f"Failed to parse item: {line}")

    payload = cast("dict[str, object]", payload_obj)
    try:
        event_type = _require_str(payload.get("type"), "event.type")
        parser = _EVENT_PARSERS.get(event_type)
        if parser is None:
            logger.warning(
                "Unknown thread event type %s; skipping. Payload=%r",
                event_type,
                payload,
            )
            return None
        return parser(payload)
    except TypeError as error:
        raise CodexThreadRunError(f"Failed to parse item: {line}") from error


def _parse_thread_started_event(payload: dict[str, object]) -> ThreadEvent:
    return ThreadStartedEvent(
        thread_id=_require_str(payload.get("thread_id"), "thread.started.thread_id"),
    )


def _parse_turn_started_event(payload: dict[str, object]) -> ThreadEvent:
    _ = payload
    return TurnStartedEvent()


def _parse_turn_completed_event(payload: dict[str, object]) -> ThreadEvent:
    usage_payload = _require_dict(payload.get("usage"), "turn.completed.usage")
    usage = Usage(
        input_tokens=_require_int(
            usage_payload.get("input_tokens"),
            "turn.completed.usage.input_tokens",
        ),
        cached_input_tokens=_require_int(
            usage_payload.get("cached_input_tokens"),
            "turn.completed.usage.cached_input_tokens",
        ),
        output_tokens=_require_int(
            usage_payload.get("output_tokens"),
            "turn.completed.usage.output_tokens",
        ),
    )
    return TurnCompletedEvent(usage=usage)


def _parse_turn_failed_event(payload: dict[str, object]) -> ThreadEvent:
    error_payload = _require_dict(payload.get("error"), "turn.failed.error")
    return TurnFailedEvent(
        error=ThreadError(
            message=_require_str(error_payload.get("message"), "turn.failed.error.message"),
        ),
    )


def _parse_item_started_event(payload: dict[str, object]) -> ThreadEvent | None:
    return _parse_item_event(payload, "item.started")


def _parse_item_updated_event(payload: dict[str, object]) -> ThreadEvent | None:
    return _parse_item_event(payload, "item.updated")


def _parse_item_completed_event(payload: dict[str, object]) -> ThreadEvent | None:
    return _parse_item_event(payload, "item.completed")


def _parse_item_event(payload: dict[str, object], event_type: str) -> ThreadEvent | None:
    item = parse_thread_item(payload.get("item"))
    if item is None:
        logger.warning(
            "Unknown thread item for %s; skipping event. Payload=%r",
            event_type,
            payload,
        )
        return None

    if event_type == "item.started":
        return ItemStartedEvent(item=item)
    if event_type == "item.updated":
        return ItemUpdatedEvent(item=item)
    return ItemCompletedEvent(item=item)


def _parse_error_event(payload: dict[str, object]) -> ThreadEvent:
    return ThreadErrorEvent(message=_require_str(payload.get("message"), "error.message"))


_EventParser = Callable[[dict[str, object]], ThreadEvent | None]
_EVENT_PARSERS: dict[str, _EventParser] = {
    "thread.started": _parse_thread_started_event,
    "turn.started": _parse_turn_started_event,
    "turn.completed": _parse_turn_completed_event,
    "turn.failed": _parse_turn_failed_event,
    "item.started": _parse_item_started_event,
    "item.updated": _parse_item_updated_event,
    "item.completed": _parse_item_completed_event,
    "error": _parse_error_event,
}


def parse_thread_item(raw: object) -> ThreadItem | None:
    item = _require_dict(raw, "thread item")
    item_type = _require_str(item.get("type"), "thread item.type")
    parser = _ITEM_PARSERS.get(item_type)
    if parser is None:
        logger.warning("Unknown thread item type %s; skipping. Payload=%r", item_type, item)
        return None
    return parser(item)


def _parse_agent_message_item(item: dict[str, object]) -> ThreadItem:
    return AgentMessageItem(
        id=_require_str(item.get("id"), "agent_message.id"),
        text=_require_str(item.get("text"), "agent_message.text"),
    )


def _parse_reasoning_item(item: dict[str, object]) -> ThreadItem:
    return ReasoningItem(
        id=_require_str(item.get("id"), "reasoning.id"),
        text=_require_str(item.get("text"), "reasoning.text"),
    )


def _parse_command_execution_item(item: dict[str, object]) -> ThreadItem:
    return CommandExecutionItem(
        id=_require_str(item.get("id"), "command_execution.id"),
        command=_require_str(item.get("command"), "command_execution.command"),
        aggregated_output=_require_str(
            item.get("aggregated_output"),
            "command_execution.aggregated_output",
        ),
        status=cast(
            "CommandExecutionStatus",
            _require_str(item.get("status"), "command_execution.status"),
        ),
        exit_code=_optional_int(item.get("exit_code"), "command_execution.exit_code"),
    )


def _parse_file_change_item(item: dict[str, object]) -> ThreadItem:
    raw_changes = _require_list(item.get("changes"), "file_change.changes")
    changes = [
        _parse_file_update_change(raw_change, index) for index, raw_change in enumerate(raw_changes)
    ]
    return FileChangeItem(
        id=_require_str(item.get("id"), "file_change.id"),
        changes=changes,
        status=cast(
            "PatchApplyStatus",
            _require_str(item.get("status"), "file_change.status"),
        ),
    )


def _parse_file_update_change(raw_change: object, index: int) -> FileUpdateChange:
    change_payload = _require_dict(raw_change, f"file_change.changes[{index}]")
    return FileUpdateChange(
        path=_require_str(change_payload.get("path"), f"file_change.changes[{index}].path"),
        kind=cast(
            "PatchChangeKind",
            _require_str(change_payload.get("kind"), f"file_change.changes[{index}].kind"),
        ),
    )


def _parse_mcp_tool_call_item(item: dict[str, object]) -> ThreadItem:
    return McpToolCallItem(
        id=_require_str(item.get("id"), "mcp_tool_call.id"),
        server=_require_str(item.get("server"), "mcp_tool_call.server"),
        tool=_require_str(item.get("tool"), "mcp_tool_call.tool"),
        arguments=item.get("arguments"),
        status=cast(
            "McpToolCallStatus",
            _require_str(item.get("status"), "mcp_tool_call.status"),
        ),
        result=_parse_mcp_result(item.get("result")),
        error=_parse_mcp_error(item.get("error")),
    )


def _parse_web_search_item(item: dict[str, object]) -> ThreadItem:
    return WebSearchItem(
        id=_require_str(item.get("id"), "web_search.id"),
        query=_require_str(item.get("query"), "web_search.query"),
    )


def _parse_todo_list_item(item: dict[str, object]) -> ThreadItem:
    raw_items = _require_list(item.get("items"), "todo_list.items")
    todo_items = [
        _parse_todo_item(raw_todo_item, index) for index, raw_todo_item in enumerate(raw_items)
    ]
    return TodoListItem(
        id=_require_str(item.get("id"), "todo_list.id"),
        items=todo_items,
    )


def _parse_todo_item(raw_todo_item: object, index: int) -> TodoItem:
    todo_payload = _require_dict(raw_todo_item, f"todo_list.items[{index}]")
    return TodoItem(
        text=_require_str(todo_payload.get("text"), f"todo_list.items[{index}].text"),
        completed=_require_bool(
            todo_payload.get("completed"),
            f"todo_list.items[{index}].completed",
        ),
    )


def _parse_error_item(item: dict[str, object]) -> ThreadItem:
    return ErrorItem(
        id=_require_str(item.get("id"), "error.id"),
        message=_require_str(item.get("message"), "error.message"),
    )


_ItemParser = Callable[[dict[str, object]], ThreadItem]
_ITEM_PARSERS: dict[str, _ItemParser] = {
    "agent_message": _parse_agent_message_item,
    "reasoning": _parse_reasoning_item,
    "command_execution": _parse_command_execution_item,
    "file_change": _parse_file_change_item,
    "mcp_tool_call": _parse_mcp_tool_call_item,
    "web_search": _parse_web_search_item,
    "todo_list": _parse_todo_list_item,
    "error": _parse_error_item,
}


def _parse_mcp_result(raw_result: object) -> McpToolCallResult | None:
    if raw_result is None:
        return None

    payload = _require_dict(raw_result, "mcp_tool_call.result")
    content = _require_list(payload.get("content"), "mcp_tool_call.result.content")
    return McpToolCallResult(
        content=content,
        structured_content=payload.get("structured_content"),
    )


def _parse_mcp_error(raw_error: object) -> McpToolCallError | None:
    if raw_error is None:
        return None

    payload = _require_dict(raw_error, "mcp_tool_call.error")
    return McpToolCallError(
        message=_require_str(payload.get("message"), "mcp_tool_call.error.message"),
    )


def _require_dict(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be an object")
    return cast("dict[str, object]", value)


def _require_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be an array")
    return value


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    return value


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field)


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a boolean")
    return value


class TurnState(NamedTuple):
    items: list[ThreadItem]
    final_response: str
    usage: Usage | None
    failure_message: str | None


def initial_turn_state() -> TurnState:
    return TurnState(items=[], final_response="", usage=None, failure_message=None)


def reduce_turn_state(state: TurnState, event: ThreadEvent) -> TurnState:
    final_response = state.final_response
    usage = state.usage
    failure_message = state.failure_message

    if isinstance(event, ItemCompletedEvent):
        state.items.append(event.item)
        if isinstance(event.item, AgentMessageItem):
            final_response = event.item.text
    elif isinstance(event, TurnCompletedEvent):
        usage = event.usage
    elif isinstance(event, TurnFailedEvent):
        failure_message = event.error.message

    return TurnState(
        items=state.items,
        final_response=final_response,
        usage=usage,
        failure_message=failure_message,
    )


def build_turn_or_raise(
    state: TurnState,
    output_type_adapter: OutputTypeAdapter[T],
) -> Turn[T]:
    if state.failure_message is not None:
        raise CodexThreadRunError(state.failure_message)

    try:
        structured_response = output_type_adapter.validate_json(state.final_response)
    except Exception as error:
        raise CodexStructuredResponseError(
            "output_type was requested but structured payload failed validation",
        ) from error

    return Turn(
        items=state.items,
        final_response=state.final_response,
        usage=state.usage,
        structured_response=structured_response,
    )
