from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import pytest

from acodex.exceptions import CodexThreadRunError, CodexThreadStreamNotConsumedError
from acodex.exec import CodexExec
from acodex.thread import Thread, _close_if_possible
from acodex.types.events import ItemCompletedEvent, ThreadStartedEvent
from acodex.types.input import Input, UserInputLocalImage, UserInputText
from acodex.types.items import AgentMessageItem
from acodex.types.turn_options import OutputSchemaInput
from tests.unit.fake_codex_executable import create_fake_codex_executable

NOT_CONSUMED_ERROR_MESSAGE = (
    "streamed.result is unavailable until streamed.events is fully consumed"
)


def test_thread_run_streamed_yields_events_and_sets_thread_id(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "thread_success", "FAKE_THREAD_ID": "thread-123"},
    )

    streamed = thread.run_streamed("hello")
    events = list(streamed.events)

    assert isinstance(events[0], ThreadStartedEvent)
    assert thread.id == "thread-123"


def test_thread_run_streamed_result_raises_before_consumption_with_exact_message(
    tmp_path: Path,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})

    streamed = thread.run_streamed("hello")

    with pytest.raises(CodexThreadStreamNotConsumedError) as error:
        _ = streamed.result
    assert str(error.value) == NOT_CONSUMED_ERROR_MESSAGE

    _close_if_possible(streamed.events)


def test_thread_run_streamed_result_raises_after_partial_consumption(tmp_path: Path) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})

    streamed = thread.run_streamed("hello")
    _ = next(streamed.events)

    with pytest.raises(CodexThreadStreamNotConsumedError) as error:
        _ = streamed.result
    assert str(error.value) == NOT_CONSUMED_ERROR_MESSAGE

    _close_if_possible(streamed.events)


def test_thread_run_streamed_result_raises_after_manual_close_before_exhaustion(
    tmp_path: Path,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})

    streamed = thread.run_streamed("hello")
    events = streamed.events
    _ = next(events)
    close_method = getattr(events, "close", None)
    assert close_method is not None
    close_method()

    with pytest.raises(CodexThreadStreamNotConsumedError) as error:
        _ = streamed.result
    assert str(error.value) == NOT_CONSUMED_ERROR_MESSAGE


def test_thread_run_streamed_result_returns_complete_turn_after_full_exhaustion(
    tmp_path: Path,
) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["draft", "final answer"]),
        },
    )

    streamed = thread.run_streamed("hello")
    _ = list(streamed.events)
    turn = streamed.result

    assert len(turn.items) == 2
    assert turn.final_response == "final answer"
    assert turn.usage is not None
    assert turn.usage.input_tokens == 10
    assert turn.usage.cached_input_tokens == 2
    assert turn.usage.output_tokens == 5
    message_texts = [item.text for item in turn.items if isinstance(item, AgentMessageItem)]
    assert len(message_texts) == len(turn.items)
    assert message_texts == ["draft", "final answer"]


def test_thread_run_streamed_result_is_stable_after_full_exhaustion(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["draft", "final answer"]),
        },
    )

    streamed = thread.run_streamed("hello")
    _ = list(streamed.events)

    first = streamed.result
    second = streamed.result

    assert first.final_response == second.final_response
    assert len(first.items) == len(second.items)
    assert first.usage == second.usage


def test_thread_run_streamed_result_raises_after_failed_turn_when_fully_exhausted(
    tmp_path: Path,
) -> None:
    message = "streamed sync failure"
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "thread_failed", "FAKE_FAILURE_MESSAGE": message},
    )

    streamed = thread.run_streamed("hello")
    _ = list(streamed.events)

    with pytest.raises(CodexThreadRunError, match=re.escape(message)):
        _ = streamed.result


def test_thread_run_returns_completed_turn_with_final_response_and_usage(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["draft", "final answer"]),
        },
    )

    turn = thread.run("hello")

    assert len(turn.items) == 2
    assert turn.final_response == "final answer"
    assert turn.usage is not None
    assert turn.usage.input_tokens == 10
    assert turn.usage.cached_input_tokens == 2
    assert turn.usage.output_tokens == 5


def test_thread_run_drains_events_after_turn_failed(tmp_path: Path) -> None:
    message = "CLI failure message"
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "lines",
            "FAKE_LINES_JSON": json.dumps(
                [
                    json.dumps({"type": "thread.started", "thread_id": "thread-before-fail"}),
                    json.dumps({"type": "turn.started"}),
                    json.dumps({"type": "turn.failed", "error": {"message": message}}),
                    json.dumps({"type": "thread.started", "thread_id": "thread-after-fail"}),
                ],
            ),
        },
    )

    with pytest.raises(CodexThreadRunError, match=re.escape(message)):
        thread.run("hello")

    assert thread.id == "thread-after-fail"


def test_thread_run_raises_codex_thread_run_error_on_turn_failed(tmp_path: Path) -> None:
    message = "CLI failure message"
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_failed",
            "FAKE_FAILURE_MESSAGE": message,
        },
    )

    with pytest.raises(CodexThreadRunError, match=re.escape(message)):
        thread.run("hello")


def test_thread_input_normalization_joins_text_and_passes_images_in_order(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "normalize_capture"},
        thread_id="thread-resume-42",
    )

    turn = thread.run(
        [
            UserInputText(text="first paragraph"),
            UserInputLocalImage(path="/images/a.png"),
            UserInputText(text="second paragraph"),
            UserInputLocalImage(path="/images/b.png"),
        ],
    )

    payload = cast("dict[str, object]", json.loads(turn.final_response))

    assert payload["stdin"] == "first paragraph\n\nsecond paragraph"
    assert payload["images"] == ["/images/a.png", "/images/b.png"]
    assert payload["resume_id"] == "thread-resume-42"
    assert _extract_flag_values(cast("list[str]", payload["argv"]), "--image") == [
        "/images/a.png",
        "/images/b.png",
    ]


def test_thread_output_schema_file_lifecycle_exhausted_stream(tmp_path: Path) -> None:
    schema: OutputSchemaInput = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "schema_check"})

    turn = thread.run("hello", output_schema=schema)
    payload = cast("dict[str, object]", json.loads(turn.final_response))
    schema_path = Path(cast("str", payload["schema_path"]))

    assert payload["schema_exists"] is True
    assert payload["schema_payload"] == schema
    assert not schema_path.exists()
    assert not schema_path.parent.exists()


def test_thread_output_schema_file_lifecycle_closed_stream(tmp_path: Path) -> None:
    schema: OutputSchemaInput = {"type": "object", "properties": {"name": {"type": "string"}}}
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "schema_check"})

    streamed = thread.run_streamed("hello", output_schema=schema)
    events = streamed.events

    _ = next(events)
    payload_event = next(events)
    assert isinstance(payload_event, ItemCompletedEvent)
    assert isinstance(payload_event.item, AgentMessageItem)
    payload = cast("dict[str, object]", json.loads(payload_event.item.text))
    schema_path = Path(cast("str", payload["schema_path"]))

    assert schema_path.exists()
    close_method = getattr(events, "close", None)
    assert close_method is not None
    close_method()

    assert not schema_path.exists()
    assert not schema_path.parent.exists()


def test_thread_run_streamed_cleanup_when_build_exec_args_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})
    schema: OutputSchemaInput = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    forced_temp_dir = tmp_path / "forced-schema-dir"

    def fake_mkdtemp(*_: object, **__: object) -> str:
        forced_temp_dir.mkdir(parents=True, exist_ok=True)
        return str(forced_temp_dir)

    monkeypatch.setattr("acodex._internal.output_schema_file.tempfile.mkdtemp", fake_mkdtemp)

    events = thread.run_streamed(cast("Input", {"bad": 1}), output_schema=schema).events
    with pytest.raises(TypeError, match=r"input must be str or list\[UserInput\], got dict"):
        next(events)

    assert not forced_temp_dir.exists()


def test_close_if_possible_is_noop_without_close() -> None:
    _close_if_possible(iter(()))


def _build_thread(
    tmp_path: Path,
    *,
    env: dict[str, str],
    thread_id: str | None = None,
) -> Thread:
    executable = create_fake_codex_executable(tmp_path)
    exec_client = CodexExec(executable_path=str(executable), env=env)
    return Thread(exec=exec_client, options={}, thread_options={}, thread_id=thread_id)


def _extract_flag_values(argv: list[str], flag: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(argv):
        if argv[index] == flag and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 2
            continue
        index += 1
    return values
