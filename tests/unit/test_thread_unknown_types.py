from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any, cast

import pytest

from acodex._internal.exec import CodexExecArgs
from acodex._internal.output_type import OutputTypeAdapter
from acodex._internal.thread_core import (
    build_turn_or_raise,
    initial_turn_state,
    normalize_input,
    parse_thread_event_jsonl,
    parse_thread_item,
    reduce_turn_state,
)
from acodex.exceptions import CodexStructuredResponseError, CodexThreadRunError
from acodex.exec import CodexExec
from acodex.thread import Thread
from acodex.types.events import ItemCompletedEvent, ThreadEvent, TurnCompletedEvent, TurnFailedEvent
from acodex.types.input import UserInputLocalImage, UserInputText
from acodex.types.items import (
    AgentMessageItem,
    CommandExecutionItem,
    ErrorItem,
    FileChangeItem,
    McpToolCallItem,
    ReasoningItem,
    TodoListItem,
    WebSearchItem,
)


def test_unknown_event_type_is_skipped_and_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    thread = _build_fake_thread(
        lines=[
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps({"type": "future.event", "payload": {"x": 1}}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 1,
                        "cached_input_tokens": 0,
                        "output_tokens": 1,
                    },
                },
            ),
        ],
    )
    caplog.set_level(logging.WARNING, logger="acodex._internal.thread_core")

    events = list(thread.run_streamed("hello").events)

    assert [event.type for event in events] == ["thread.started", "turn.completed"]
    assert "Unknown thread event type future.event; skipping." in caplog.text


def test_unknown_item_type_event_is_skipped_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    thread = _build_fake_thread(
        lines=[
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "future.item", "id": "future-item"},
                },
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 2,
                        "cached_input_tokens": 0,
                        "output_tokens": 3,
                    },
                },
            ),
        ],
    )
    caplog.set_level(logging.WARNING, logger="acodex._internal.thread_core")

    events = list(thread.run_streamed("hello").events)

    assert [event.type for event in events] == ["thread.started", "turn.completed"]
    assert "Unknown thread item type future.item; skipping." in caplog.text
    assert "Unknown thread item for item.completed; skipping event." in caplog.text


def test_parse_thread_event_jsonl_invalid_json_raises_codex_thread_run_error() -> None:
    with pytest.raises(CodexThreadRunError, match="Failed to parse item: not-json"):
        parse_thread_event_jsonl("not-json")


def test_parse_thread_event_jsonl_rejects_non_object_payload() -> None:
    with pytest.raises(CodexThreadRunError, match=re.escape("Failed to parse item: []")):
        parse_thread_event_jsonl("[]")


def test_parse_thread_event_jsonl_wraps_type_errors_from_parsers() -> None:
    line = json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": "x",
                "cached_input_tokens": 0,
                "output_tokens": 1,
            },
        },
    )

    with pytest.raises(CodexThreadRunError, match=re.escape(f"Failed to parse item: {line}")):
        parse_thread_event_jsonl(line)


def test_normalize_input_handles_string_and_list() -> None:
    from_string = normalize_input("hello")
    assert from_string.prompt == "hello"
    assert from_string.images == []

    from_list = normalize_input(
        [
            UserInputText(text="alpha"),
            UserInputLocalImage(path="/images/a.png"),
            UserInputText(text="beta"),
        ],
    )
    assert from_list.prompt == "alpha\n\nbeta"
    assert from_list.images == ["/images/a.png"]


def test_normalize_input_rejects_invalid_shapes() -> None:
    with pytest.raises(TypeError, match=r"input must be str or list\[UserInput\], got dict"):
        normalize_input(cast("Any", {"type": "text"}))

    with pytest.raises(
        TypeError,
        match="input\\[0\\] must be UserInputText or UserInputLocalImage",
    ):
        normalize_input(cast("Any", [{"type": "text", "text": 1}]))

    with pytest.raises(
        TypeError,
        match="input\\[0\\] must be UserInputText or UserInputLocalImage",
    ):
        normalize_input(cast("Any", [{"type": "future", "x": "y"}]))


def test_parse_thread_item_supports_all_public_item_variants() -> None:
    agent_item = parse_thread_item({"type": "agent_message", "id": "a", "text": "hello"})
    reasoning_item = parse_thread_item({"type": "reasoning", "id": "r", "text": "why"})
    command_item = parse_thread_item(
        {
            "type": "command_execution",
            "id": "c",
            "command": "ls",
            "aggregated_output": "ok",
            "status": "completed",
            "exit_code": 0,
        },
    )
    file_change_item = parse_thread_item(
        {
            "type": "file_change",
            "id": "f",
            "status": "completed",
            "changes": [{"path": "x.py", "kind": "update"}],
        },
    )
    mcp_item = parse_thread_item(
        {
            "type": "mcp_tool_call",
            "id": "m",
            "server": "srv",
            "tool": "tool",
            "arguments": {"x": 1},
            "status": "completed",
            "result": {"content": [{"type": "text", "text": "ok"}], "structured_content": {"a": 1}},
            "error": {"message": "not-used"},
        },
    )
    web_item = parse_thread_item({"type": "web_search", "id": "w", "query": "q"})
    todo_item = parse_thread_item(
        {
            "type": "todo_list",
            "id": "t",
            "items": [{"text": "step", "completed": False}],
        },
    )
    error_item = parse_thread_item({"type": "error", "id": "e", "message": "oops"})

    assert isinstance(agent_item, AgentMessageItem)
    assert isinstance(reasoning_item, ReasoningItem)
    assert isinstance(command_item, CommandExecutionItem)
    assert isinstance(file_change_item, FileChangeItem)
    assert isinstance(mcp_item, McpToolCallItem)
    assert isinstance(web_item, WebSearchItem)
    assert isinstance(todo_item, TodoListItem)
    assert isinstance(error_item, ErrorItem)


def test_parse_item_started_event_is_supported() -> None:
    event = parse_thread_event_jsonl(
        json.dumps(
            {
                "type": "item.started",
                "item": {"type": "agent_message", "id": "a", "text": "hello"},
            },
        ),
    )

    assert event is not None
    assert event.type == "item.started"


def test_parse_mcp_tool_call_allows_missing_result_and_error() -> None:
    item = parse_thread_item(
        {
            "type": "mcp_tool_call",
            "id": "mcp-1",
            "server": "srv",
            "tool": "run",
            "arguments": {"x": 1},
            "status": "in_progress",
        },
    )

    assert isinstance(item, McpToolCallItem)
    assert item.result is None
    assert item.error is None


def test_parse_thread_item_command_execution_exit_code_is_optional() -> None:
    item = parse_thread_item(
        {
            "type": "command_execution",
            "id": "c-1",
            "command": "ls",
            "aggregated_output": "ok",
            "status": "in_progress",
        },
    )

    assert isinstance(item, CommandExecutionItem)
    assert item.exit_code is None


def test_parse_thread_item_rejects_invalid_shapes_with_field_messages() -> None:
    with pytest.raises(TypeError, match="thread item must be an object"):
        parse_thread_item("not-an-object")

    with pytest.raises(TypeError, match=re.escape("web_search.id must be a string")):
        parse_thread_item({"type": "web_search", "id": 123, "query": "q"})

    with pytest.raises(TypeError, match=re.escape("todo_list.items must be an array")):
        parse_thread_item({"type": "todo_list", "id": "t", "items": "nope"})

    with pytest.raises(
        TypeError,
        match=re.escape("todo_list.items[0].completed must be a boolean"),
    ):
        parse_thread_item(
            {
                "type": "todo_list",
                "id": "t",
                "items": [{"text": "task", "completed": "no"}],
            },
        )


def test_parse_thread_event_jsonl_parses_event_variants() -> None:
    started = parse_thread_event_jsonl(json.dumps({"type": "turn.started"}))
    updated = parse_thread_event_jsonl(
        json.dumps(
            {
                "type": "item.updated",
                "item": {"type": "agent_message", "id": "a", "text": "hello"},
            },
        ),
    )
    error = parse_thread_event_jsonl(json.dumps({"type": "error", "message": "fatal"}))

    assert started is not None
    assert started.type == "turn.started"
    assert updated is not None
    assert updated.type == "item.updated"
    assert error is not None
    assert error.type == "error"


def test_turn_state_reduction_builds_turn_and_raises_on_failure() -> None:
    completed_state = initial_turn_state()
    completed_events: list[ThreadEvent] = [
        cast(
            "ItemCompletedEvent",
            parse_thread_event_jsonl(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "id": "a", "text": "hello"},
                    },
                ),
            ),
        ),
        cast(
            "TurnCompletedEvent",
            parse_thread_event_jsonl(
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 3,
                            "cached_input_tokens": 1,
                            "output_tokens": 2,
                        },
                    },
                ),
            ),
        ),
    ]
    for event in completed_events:
        completed_state = reduce_turn_state(completed_state, event)

    output_type_adapter: OutputTypeAdapter[str] = OutputTypeAdapter()
    turn = build_turn_or_raise(completed_state, output_type_adapter=output_type_adapter)
    assert turn.final_response == "hello"
    with pytest.raises(
        CodexStructuredResponseError,
        match=(
            "No output schema available for validating structured response\\. "
            "Provide an `output_type` or `output_schema` to enable validation\\."
        ),
    ):
        _ = turn.structured_response
    assert turn.usage is not None
    assert turn.usage.output_tokens == 2
    assert len(turn.items) == 1

    failed_state = initial_turn_state()
    failed_event = cast(
        "TurnFailedEvent",
        parse_thread_event_jsonl(
            json.dumps({"type": "turn.failed", "error": {"message": "failed"}}),
        ),
    )
    failed_state = reduce_turn_state(failed_state, failed_event)

    with pytest.raises(CodexThreadRunError, match="failed"):
        build_turn_or_raise(failed_state, output_type_adapter=OutputTypeAdapter[str]())


def test_reduce_turn_state_does_not_set_final_response_for_non_agent_item() -> None:
    state = initial_turn_state()
    event = ItemCompletedEvent(item=ReasoningItem(id="r-1", text="thinking"))

    reduced = reduce_turn_state(state, event)

    assert not reduced.final_response


class _FakeExec:
    def __init__(self, *, lines: list[str]) -> None:
        self._lines = lines

    def run(self, args: CodexExecArgs) -> Iterator[str]:
        _ = args
        yield from self._lines


def _build_fake_thread(*, lines: list[str]) -> Thread:
    fake_exec = cast("CodexExec", _FakeExec(lines=lines))
    return Thread(exec=fake_exec, options={}, thread_options={})
