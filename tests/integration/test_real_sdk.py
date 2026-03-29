from __future__ import annotations

import asyncio
import json
from enum import Enum
from pathlib import Path
from typing import Generic, Literal, TypeVar

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


def test_codex_run_returns_complex_validated_pydantic_structured_output(
    real_model: str,
    real_working_directory: Path,
) -> None:
    try:
        from pydantic import BaseModel
    except ModuleNotFoundError as error:
        if error.name in {"pydantic", "pydantic_core"}:
            pytest.skip("Pydantic is not available in this interpreter.")
        raise

    value_t = TypeVar("value_t")

    class ReleaseType(str, Enum):
        MAJOR = "major"
        MINOR = "minor"
        PATCH = "patch"

    class ReleaseChannel(str, Enum):
        STABLE = "stable"
        BETA = "beta"
        CANARY = "canary"

    class ArtifactKind(str, Enum):
        WHEEL = "wheel"
        DOCS = "docs"
        SBOM = "sbom"

    class ApprovalStatus(str, Enum):
        APPROVED = "approved"
        PENDING = "pending"

    class LabeledValue(BaseModel, Generic[value_t]):
        label: str
        value: value_t

    class CollectionPage(BaseModel, Generic[value_t]):
        total: int
        items: list[value_t]

    class ReleaseOwner(BaseModel):
        team: str
        primary_contact: str
        escalation_contacts: list[str]

    class ReleaseArtifact(BaseModel):
        kind: ArtifactKind
        name: str
        checksum: str
        mirrors: list[LabeledValue[str]]

    class RolloutPhase(BaseModel):
        name: str
        audience_percent: int
        metrics: list[LabeledValue[int]]

    class ReleaseApproval(BaseModel):
        reviewer: str
        status: ApprovalStatus

    class ReleaseRecord(BaseModel):
        version: str
        release_type: ReleaseType
        channels: list[ReleaseChannel]
        owner: ReleaseOwner
        artifacts: CollectionPage[ReleaseArtifact]
        rollout_phases: list[RolloutPhase]
        approvals: list[ReleaseApproval]
        metadata: dict[str, str]
        highlights: list[str]

    class ReleaseEnvelope(BaseModel):
        status: Literal["ok"]
        release: ReleaseRecord
        related_versions: CollectionPage[LabeledValue[str]]
        summary: str

    expected_payload = {
        "status": "ok",
        "release": {
            "version": "2.4.0",
            "release_type": "minor",
            "channels": ["stable", "beta"],
            "owner": {
                "team": "sdk-platform",
                "primary_contact": "sdk@example.com",
                "escalation_contacts": ["lead@example.com", "ops@example.com"],
            },
            "artifacts": {
                "total": 3,
                "items": [
                    {
                        "kind": "wheel",
                        "name": "acodex-2.4.0-py3-none-any.whl",
                        "checksum": "sha256:wheel-240",
                        "mirrors": [
                            {
                                "label": "primary",
                                "value": "https://example.com/downloads/acodex-2.4.0.whl",
                            },
                            {
                                "label": "backup",
                                "value": "https://mirror.example.com/acodex-2.4.0.whl",
                            },
                        ],
                    },
                    {
                        "kind": "docs",
                        "name": "acodex-2.4.0-docs.tar.gz",
                        "checksum": "sha256:docs-240",
                        "mirrors": [
                            {
                                "label": "primary",
                                "value": "https://example.com/downloads/acodex-2.4.0-docs.tar.gz",
                            },
                        ],
                    },
                    {
                        "kind": "sbom",
                        "name": "acodex-2.4.0.spdx.json",
                        "checksum": "sha256:sbom-240",
                        "mirrors": [
                            {
                                "label": "primary",
                                "value": "https://example.com/downloads/acodex-2.4.0.spdx.json",
                            },
                        ],
                    },
                ],
            },
            "rollout_phases": [
                {
                    "name": "pilot",
                    "audience_percent": 10,
                    "metrics": [
                        {"label": "error_budget_remaining", "value": 99},
                        {"label": "support_tickets", "value": 0},
                    ],
                },
                {
                    "name": "general",
                    "audience_percent": 100,
                    "metrics": [
                        {"label": "error_budget_remaining", "value": 97},
                        {"label": "support_tickets", "value": 3},
                    ],
                },
            ],
            "approvals": [
                {"reviewer": "release-bot", "status": "approved"},
                {"reviewer": "qa-lead", "status": "pending"},
            ],
            "metadata": {
                "ticket": "REL-240",
                "release_train": "2026.03",
                "backward_compatible": "true",
            },
            "highlights": [
                "Adds nested structured output coverage for the Python SDK.",
                "Exercises enum validation and multiple generic container shapes.",
            ],
        },
        "related_versions": {
            "total": 2,
            "items": [
                {"label": "previous", "value": "2.3.1"},
                {"label": "next_planned", "value": "2.5.0"},
            ],
        },
        "summary": "Minor SDK release with staged rollout metadata.",
    }

    client = Codex()
    thread = client.start_thread(**_build_thread_options(real_model, real_working_directory))
    turn = thread.run(
        "Do not use tools. Return only JSON that exactly matches this object. "
        "Do not add markdown, code fences, or any explanation.\n"
        f"{json.dumps(expected_payload, indent=2)}",
        output_type=ReleaseEnvelope,
    )
    payload = turn.structured_response

    assert isinstance(payload, ReleaseEnvelope)
    assert payload.release.release_type is ReleaseType.MINOR
    assert payload.release.channels == [ReleaseChannel.STABLE, ReleaseChannel.BETA]
    assert payload.release.artifacts.items[0].kind is ArtifactKind.WHEEL
    assert payload.release.artifacts.items[1].kind is ArtifactKind.DOCS
    assert payload.release.approvals[0].status is ApprovalStatus.APPROVED
    assert payload.release.approvals[1].status is ApprovalStatus.PENDING
    assert payload.model_dump(mode="json") == expected_payload


def _build_thread_options(real_model: str, real_working_directory: Path) -> ThreadOptions:
    return ThreadOptions(
        model=real_model,
        sandbox_mode="read-only",
        working_directory=str(real_working_directory),
        skip_git_repo_check=True,
        web_search_enabled=False,
    )
