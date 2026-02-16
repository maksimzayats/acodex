from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import cast

import pytest
from typing_extensions import TypedDict

from acodex.exceptions import (
    CodexStructuredResponseError,
    CodexThreadRunError,
    CodexThreadStreamNotConsumedError,
)
from acodex.exec import AsyncCodexExec
from acodex.thread import AsyncThread, _aclose_if_possible
from acodex.types.events import ItemCompletedEvent, ThreadStartedEvent
from acodex.types.input import Input, UserInputLocalImage, UserInputText
from acodex.types.items import AgentMessageItem
from acodex.types.turn_options import OutputSchemaInput
from tests.unit.fake_codex_executable import create_fake_codex_executable

NOT_CONSUMED_ERROR_MESSAGE = (
    "streamed.result is unavailable until streamed.events is fully consumed"
)


class _StructuredPayload(TypedDict):
    status: str
    count: int


def test_async_thread_run_streamed_yields_events_and_sets_thread_id(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "thread_success", "FAKE_THREAD_ID": "async-thread-123"},
    )

    async def run() -> list[object]:
        streamed = await thread.run_streamed("hello")
        return [event async for event in streamed.events]

    events = asyncio.run(run())

    assert isinstance(events[0], ThreadStartedEvent)
    assert thread.id == "async-thread-123"


def test_async_thread_run_streamed_result_raises_before_consumption_with_exact_message(
    tmp_path: Path,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})

    async def run() -> None:
        streamed = await thread.run_streamed("hello")
        with pytest.raises(CodexThreadStreamNotConsumedError) as error:
            _ = streamed.result
        assert str(error.value) == NOT_CONSUMED_ERROR_MESSAGE
        await _aclose_if_possible(streamed.events)

    asyncio.run(run())


def test_async_thread_run_streamed_result_raises_after_partial_consumption(
    tmp_path: Path,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})

    async def run() -> None:
        streamed = await thread.run_streamed("hello")
        _ = await anext(streamed.events)
        with pytest.raises(CodexThreadStreamNotConsumedError) as error:
            _ = streamed.result
        assert str(error.value) == NOT_CONSUMED_ERROR_MESSAGE
        await _aclose_if_possible(streamed.events)

    asyncio.run(run())


def test_async_thread_run_streamed_result_raises_after_manual_close_before_exhaustion(
    tmp_path: Path,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})

    async def run() -> None:
        streamed = await thread.run_streamed("hello")
        _ = await anext(streamed.events)
        await streamed.events.aclose()
        with pytest.raises(CodexThreadStreamNotConsumedError) as error:
            _ = streamed.result
        assert str(error.value) == NOT_CONSUMED_ERROR_MESSAGE

    asyncio.run(run())


def test_async_thread_run_streamed_result_returns_complete_turn_after_full_exhaustion(
    tmp_path: Path,
) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["draft", "async final"]),
        },
    )

    async def run() -> tuple[str, int | None, int, list[str]]:
        streamed = await thread.run_streamed("hello")
        _ = [event async for event in streamed.events]
        turn = streamed.result
        output_tokens = turn.usage.output_tokens if turn.usage is not None else None
        message_texts = [item.text for item in turn.items if isinstance(item, AgentMessageItem)]
        return turn.final_response, output_tokens, len(turn.items), message_texts

    final_response, output_tokens, item_count, message_texts = asyncio.run(run())

    assert final_response == "async final"
    assert output_tokens == 5
    assert item_count == 2
    assert message_texts == ["draft", "async final"]


def test_async_thread_run_streamed_result_is_stable_after_full_exhaustion(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["draft", "async final"]),
        },
    )

    async def run() -> tuple[str, str, int, int, int | None, int | None]:
        streamed = await thread.run_streamed("hello")
        _ = [event async for event in streamed.events]
        first = streamed.result
        second = streamed.result
        first_output = first.usage.output_tokens if first.usage is not None else None
        second_output = second.usage.output_tokens if second.usage is not None else None
        return (
            first.final_response,
            second.final_response,
            len(first.items),
            len(second.items),
            first_output,
            second_output,
        )

    (
        first_final_response,
        second_final_response,
        first_item_count,
        second_item_count,
        first_output_tokens,
        second_output_tokens,
    ) = asyncio.run(run())

    assert first_final_response == second_final_response
    assert first_item_count == second_item_count
    assert first_output_tokens == second_output_tokens


def test_async_thread_run_streamed_result_raises_after_failed_turn_when_fully_exhausted(
    tmp_path: Path,
) -> None:
    message = "streamed async failure"
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "thread_failed", "FAKE_FAILURE_MESSAGE": message},
    )

    async def run() -> None:
        streamed = await thread.run_streamed("hello")
        _ = [event async for event in streamed.events]
        _ = streamed.result

    with pytest.raises(CodexThreadRunError, match=re.escape(message)):
        asyncio.run(run())


def test_async_thread_run_returns_completed_turn_with_final_response_and_usage(
    tmp_path: Path,
) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["draft", "async final"]),
        },
    )

    async def run() -> tuple[str, str, int | None]:
        turn = await thread.run("hello")
        output_tokens = turn.usage.output_tokens if turn.usage is not None else None
        return turn.final_response, turn.structured_response, output_tokens

    final_response, structured_response, output_tokens = asyncio.run(run())

    assert final_response == "async final"
    assert structured_response == final_response
    assert output_tokens == 5


def test_async_thread_run_parses_json_when_only_output_schema_is_provided(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(['{"status":"ok","count":1}']),
        },
    )

    async def run() -> dict[str, object]:
        turn = await thread.run("hello", output_schema={"type": "object"})
        return cast("dict[str, object]", turn.structured_response)

    payload = asyncio.run(run())
    assert payload == {"status": "ok", "count": 1}


def test_async_thread_run_validates_payload_when_output_type_is_provided(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(['{"status":"ok","count":1}']),
        },
    )

    async def run() -> _StructuredPayload:
        turn = await thread.run("hello", output_type=_StructuredPayload)
        return turn.structured_response

    payload = asyncio.run(run())
    assert payload == {"status": "ok", "count": 1}


def test_async_thread_run_raises_on_invalid_output_type_payload(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(['{"status":"ok","count":"bad"}']),
        },
    )

    async def run() -> None:
        await thread.run("hello", output_type=_StructuredPayload)

    with pytest.raises(CodexStructuredResponseError):
        asyncio.run(run())


def test_async_thread_run_raises_on_invalid_json_with_output_schema_only(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_RESPONSES_JSON": json.dumps(["plain text"]),
        },
    )

    async def run() -> None:
        await thread.run("hello", output_schema={"type": "object"})

    with pytest.raises(CodexStructuredResponseError):
        asyncio.run(run())


def test_async_thread_run_drains_events_after_turn_failed(tmp_path: Path) -> None:
    message = "async CLI failure"
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

    async def run() -> None:
        await thread.run("hello")

    with pytest.raises(CodexThreadRunError, match=re.escape(message)):
        asyncio.run(run())

    assert thread.id == "thread-after-fail"


def test_async_thread_run_raises_codex_thread_run_error_on_turn_failed(tmp_path: Path) -> None:
    message = "async CLI failure"
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "thread_failed", "FAKE_FAILURE_MESSAGE": message},
    )

    async def run() -> None:
        await thread.run("hello")

    with pytest.raises(CodexThreadRunError, match=re.escape(message)):
        asyncio.run(run())


def test_async_thread_input_normalization_joins_text_and_passes_images_in_order(
    tmp_path: Path,
) -> None:
    thread = _build_thread(
        tmp_path,
        env={"FAKE_CODEX_MODE": "normalize_capture"},
        thread_id="async-resume-1",
    )

    async def run() -> dict[str, object]:
        turn = await thread.run(
            [
                UserInputText(text="first paragraph"),
                UserInputLocalImage(path="/images/a.png"),
                UserInputText(text="second paragraph"),
                UserInputLocalImage(path="/images/b.png"),
            ],
        )
        return cast("dict[str, object]", json.loads(turn.final_response))

    payload = asyncio.run(run())

    assert payload["stdin"] == "first paragraph\n\nsecond paragraph"
    assert payload["images"] == ["/images/a.png", "/images/b.png"]
    assert payload["resume_id"] == "async-resume-1"
    assert _extract_flag_values(cast("list[str]", payload["argv"]), "--image") == [
        "/images/a.png",
        "/images/b.png",
    ]


def test_async_thread_output_schema_file_lifecycle_exhausted_and_closed_stream(
    tmp_path: Path,
) -> None:
    schema: OutputSchemaInput = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    exhausted_thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "schema_check"})
    closed_thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "schema_check"})

    async def run_exhausted() -> dict[str, object]:
        turn = await exhausted_thread.run("hello", output_schema=schema)
        return cast("dict[str, object]", json.loads(turn.final_response))

    exhausted_payload = asyncio.run(run_exhausted())
    exhausted_path = Path(cast("str", exhausted_payload["schema_path"]))
    assert exhausted_payload["schema_exists"] is True
    assert exhausted_payload["schema_payload"] == schema
    assert not exhausted_path.exists()
    assert not exhausted_path.parent.exists()

    async def run_closed() -> tuple[Path, bool]:
        streamed = await closed_thread.run_streamed("hello", output_schema=schema)
        events = streamed.events
        _ = await anext(events)
        payload_event = await anext(events)
        assert isinstance(payload_event, ItemCompletedEvent)
        assert isinstance(payload_event.item, AgentMessageItem)
        payload = cast("dict[str, object]", json.loads(payload_event.item.text))
        schema_path = Path(cast("str", payload["schema_path"]))
        before_close_exists = bool(payload["schema_exists"])
        close_method = getattr(events, "aclose", None)
        assert close_method is not None
        await close_method()
        return schema_path, before_close_exists

    closed_path, before_close_exists = asyncio.run(run_closed())
    assert before_close_exists
    assert not closed_path.exists()
    assert not closed_path.parent.exists()


def test_async_thread_run_streamed_skips_unknown_events(tmp_path: Path) -> None:
    thread = _build_thread(
        tmp_path,
        env={
            "FAKE_CODEX_MODE": "lines",
            "FAKE_LINES_JSON": json.dumps(
                [
                    json.dumps({"type": "future.event", "payload": {"x": 1}}),
                    json.dumps({"type": "thread.started", "thread_id": "thread-async-known"}),
                ],
            ),
        },
    )

    async def run() -> list[object]:
        streamed = await thread.run_streamed("hello")
        return [event async for event in streamed.events]

    events = asyncio.run(run())

    assert len(events) == 1
    assert isinstance(events[0], ThreadStartedEvent)
    assert thread.id == "thread-async-known"


def test_async_thread_run_streamed_cleanup_when_build_exec_args_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _build_thread(tmp_path, env={"FAKE_CODEX_MODE": "thread_success"})
    schema: OutputSchemaInput = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    forced_temp_dir = tmp_path / "forced-async-schema-dir"

    def fake_mkdtemp(*_: object, **__: object) -> str:
        forced_temp_dir.mkdir(parents=True, exist_ok=True)
        return str(forced_temp_dir)

    monkeypatch.setattr("acodex._internal.output_schema_file.tempfile.mkdtemp", fake_mkdtemp)

    async def run() -> None:
        streamed = await thread.run_streamed(cast("Input", {"bad": 1}), output_schema=schema)
        with pytest.raises(TypeError, match=r"input must be str or list\[UserInput\], got dict"):
            await anext(streamed.events)

    asyncio.run(run())

    assert not forced_temp_dir.exists()


def test_aclose_if_possible_is_noop_without_aclose() -> None:
    asyncio.run(_aclose_if_possible(object()))


def _build_thread(
    tmp_path: Path,
    *,
    env: dict[str, str],
    thread_id: str | None = None,
) -> AsyncThread:
    executable = create_fake_codex_executable(tmp_path)
    exec_client = AsyncCodexExec(executable_path=str(executable), env=env)
    return AsyncThread(exec=exec_client, options={}, thread_options={}, thread_id=thread_id)


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
