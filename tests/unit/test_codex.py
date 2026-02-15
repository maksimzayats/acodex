from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from acodex.codex import AsyncCodex, Codex
from acodex.types.input import UserInputLocalImage, UserInputText
from tests.unit.fake_codex_executable import create_fake_codex_executable


def test_codex_start_thread_runs_with_fake_executable(tmp_path: Path) -> None:
    executable = create_fake_codex_executable(tmp_path)
    client = Codex(
        codex_path_override=str(executable),
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_THREAD_ID": "codex-thread-sync",
            "FAKE_RESPONSES_JSON": json.dumps(["sync response"]),
        },
    )

    thread = client.start_thread()
    turn = thread.run("hello")

    assert thread.id == "codex-thread-sync"
    assert turn.final_response == "sync response"


def test_codex_resume_thread_forwards_resume_id(tmp_path: Path) -> None:
    executable = create_fake_codex_executable(tmp_path)
    client = Codex(
        codex_path_override=str(executable),
        env={
            "FAKE_CODEX_MODE": "normalize_capture",
        },
    )

    thread = client.resume_thread("thread-xyz")
    turn = thread.run(
        [
            UserInputText(text="hello"),
            UserInputLocalImage(path="/images/a.png"),
        ],
    )
    payload = cast("dict[str, object]", json.loads(turn.final_response))
    argv = cast("list[str]", payload["argv"])

    assert payload["resume_id"] == "thread-xyz"
    assert argv[argv.index("resume") + 1] == "thread-xyz"
    assert argv.index("resume") < argv.index("--image")


def test_async_codex_start_thread_runs_with_fake_executable(tmp_path: Path) -> None:
    executable = create_fake_codex_executable(tmp_path)
    client = AsyncCodex(
        codex_path_override=str(executable),
        env={
            "FAKE_CODEX_MODE": "thread_success",
            "FAKE_THREAD_ID": "codex-thread-async",
            "FAKE_RESPONSES_JSON": json.dumps(["async response"]),
        },
    )

    async def run() -> tuple[str | None, str]:
        thread = client.start_thread()
        turn = await thread.run("hello")
        return thread.id, turn.final_response

    thread_id, final_response = asyncio.run(run())

    assert thread_id == "codex-thread-async"
    assert final_response == "async response"


def test_async_codex_resume_thread_forwards_resume_id(tmp_path: Path) -> None:
    executable = create_fake_codex_executable(tmp_path)
    client = AsyncCodex(
        codex_path_override=str(executable),
        env={
            "FAKE_CODEX_MODE": "normalize_capture",
        },
    )

    async def run() -> dict[str, object]:
        thread = client.resume_thread("thread-xyz")
        turn = await thread.run(
            [
                UserInputText(text="hello"),
                UserInputLocalImage(path="/images/a.png"),
            ],
        )
        return cast("dict[str, object]", json.loads(turn.final_response))

    payload = asyncio.run(run())
    argv = cast("list[str]", payload["argv"])

    assert payload["resume_id"] == "thread-xyz"
    assert argv[argv.index("resume") + 1] == "thread-xyz"
    assert argv.index("resume") < argv.index("--image")
