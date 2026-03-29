from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

import pytest

from acodex import (
    AsyncCodex,
    Codex,
    ItemCompletedEvent,
    ThreadOptions,
    ThreadStartedEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
)

pytestmark = pytest.mark.real_integration


def test_codex_start_thread_run_returns_expected_plain_response(
    real_model: str,
    real_working_directory: Path,
) -> None:
    response_marker = "ACODEX_SYNC_PLAIN_OK"
    client = Codex()
    thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))

    turn = thread.run(
        f"Do not use tools. Reply with exactly {response_marker} and nothing else.",
    )

    assert thread.id is not None
    assert turn.items
    assert turn.final_response.strip() == response_marker


def test_codex_resume_thread_preserves_context_across_turns(
    real_model: str,
    real_working_directory: Path,
) -> None:
    remembered_value = "ACODEX_RESUME_VALUE_7319"
    client = Codex()
    thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))

    first_turn = thread.run(
        "Do not use tools. Remember this exact token for the next turn: "
        f"{remembered_value}. Reply with exactly READY and nothing else.",
    )
    thread_id = thread.id

    assert first_turn.final_response.strip() == "READY"
    assert thread_id is not None

    resumed = client.resume_thread(
        thread_id,
        **_build_thread_options(real_model, real_working_directory),
    )
    second_turn = resumed.run(
        "Do not use tools. Return the exact token I asked you to remember in the previous turn. "
        "Reply with only the token.",
    )

    assert resumed.id == thread_id
    assert second_turn.final_response.strip() == remembered_value


def test_codex_run_returns_json_when_output_schema_is_provided(
    real_model: str,
    real_working_directory: Path,
) -> None:
    client = Codex()
    thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))
    turn = thread.run(
        'Do not use tools. Return only JSON with status "ok" and count 1.',
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "const": "ok"},
                "count": {"type": "integer", "const": 1},
            },
            "required": ["status", "count"],
            "additionalProperties": False,
        },
    )

    assert turn.structured_response == {"status": "ok", "count": 1}


def test_codex_run_streamed_yields_expected_events_and_result(
    real_model: str,
    real_working_directory: Path,
) -> None:
    response_marker = "ACODEX_SYNC_STREAM_OK"
    client = Codex()
    thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))

    streamed = thread.run_streamed(
        f"Do not use tools. Reply with exactly {response_marker} and nothing else.",
    )
    events = list(streamed.events)
    turn = streamed.result

    assert any(isinstance(event, ThreadStartedEvent) for event in events)
    assert any(isinstance(event, TurnStartedEvent) for event in events)
    assert any(isinstance(event, ItemCompletedEvent) for event in events)
    assert any(isinstance(event, TurnCompletedEvent) for event in events)
    assert turn.items
    assert turn.final_response.strip() == response_marker


def test_async_codex_run_streamed_yields_parsed_events_end_to_end(
    real_model: str,
    real_working_directory: Path,
) -> None:
    response_marker = "ACODEX_ASYNC_STREAM_OK"

    async def run() -> tuple[bool, bool, bool, bool, str, int]:
        client = AsyncCodex()
        thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))
        streamed = await thread.run_streamed(
            f"Do not use tools. Reply with exactly {response_marker} and nothing else.",
        )
        events = [event async for event in streamed.events]
        turn = streamed.result
        return (
            any(isinstance(event, ThreadStartedEvent) for event in events),
            any(isinstance(event, TurnStartedEvent) for event in events),
            any(isinstance(event, ItemCompletedEvent) for event in events),
            any(isinstance(event, TurnCompletedEvent) for event in events),
            turn.final_response.strip(),
            len(turn.items),
        )

    (
        has_thread_started,
        has_turn_started,
        has_item_completed,
        has_turn_completed,
        final_response,
        item_count,
    ) = asyncio.run(run())

    assert has_thread_started
    assert has_turn_started
    assert has_item_completed
    assert has_turn_completed
    assert item_count > 0
    assert final_response == response_marker


def test_codex_run_returns_validated_pydantic_structured_output(
    real_model: str,
    real_working_directory: Path,
) -> None:
    try:
        from pydantic import BaseModel
    except ModuleNotFoundError as error:
        if error.name in {"pydantic", "pydantic_core"}:
            pytest.skip("Pydantic is not available in this interpreter.")
        raise

    class StructuredPayload(BaseModel):
        status: Literal["ok"]
        count: int

    client = Codex()
    thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))
    turn = thread.run(
        'Do not use tools. Return only JSON with status "ok" and count 1.',
        output_type=StructuredPayload,
    )
    payload = turn.structured_response

    assert isinstance(payload, StructuredPayload)
    assert payload.model_dump() == {"status": "ok", "count": 1}


def _build_thread_options(real_model: str, real_working_directory: Path) -> ThreadOptions:
    return ThreadOptions(
        model=real_model,
        sandbox_mode="read-only",
        working_directory=str(real_working_directory),
        skip_git_repo_check=True,
        web_search_enabled=False,
    )
