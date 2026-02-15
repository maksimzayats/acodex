from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from acodex.exec import AsyncCodexExec, CodexExec
from tests.unit.fake_codex_executable import create_fake_codex_executable


def test_codex_exec_run_streams_stdout_lines(tmp_path: Path) -> None:
    executable = create_fake_codex_executable(tmp_path)
    client = CodexExec(
        executable_path=str(executable),
        env={
            "FAKE_CODEX_MODE": "lines",
            "FAKE_LINES_JSON": json.dumps(["first", "second", "third"]),
        },
    )

    lines = list(client.run({"input": "hello"}))

    assert lines == ["first", "second", "third"]


def test_async_codex_exec_run_streams_stdout_lines(tmp_path: Path) -> None:
    executable = create_fake_codex_executable(tmp_path)
    client = AsyncCodexExec(
        executable_path=str(executable),
        env={
            "FAKE_CODEX_MODE": "lines",
            "FAKE_LINES_JSON": json.dumps(["async-first", "async-second"]),
        },
    )

    async def run() -> list[str]:
        return [line async for line in client.run({"input": "hello"})]

    assert asyncio.run(run()) == ["async-first", "async-second"]


def test_exec_env_empty_overrides_prevent_parent_env_inheritance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = create_fake_codex_executable(tmp_path)
    marker_name = "ACODEX_PARENT_MARKER"
    monkeypatch.setenv(marker_name, "1")
    client = CodexExec(
        executable_path=str(executable),
        env={
            "FAKE_CODEX_MODE": "env_guard",
            "FAKE_MARKER_NAME": marker_name,
        },
    )

    lines = list(client.run({"input": "hello"}))

    assert lines == ["clean"]
