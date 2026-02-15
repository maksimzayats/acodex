from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
from collections.abc import Coroutine
from pathlib import Path
from textwrap import dedent
from typing import TypeVar

import pytest

from acodex._internal.exec import CodexExecCommand
from acodex._internal.process_runner import AsyncCodexProcessRunner, SyncCodexProcessRunner
from acodex.exceptions import CodexCancelledError, CodexExecError

_T = TypeVar("_T")


def test_sync_stream_lines_yields_stdout_lines_without_newlines(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = SyncCodexProcessRunner(executable_path=str(executable))
    command = _build_command(mode="stdout_lines")

    lines = list(runner.stream_lines(command))

    assert lines == ["first line", "second line", "third line"]


def test_sync_nonzero_exit_raises_codex_exec_error_includes_stderr(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = SyncCodexProcessRunner(executable_path=str(executable))
    command = _build_command(mode="nonzero")

    with pytest.raises(CodexExecError, match=re.escape("Codex Exec exited with code 7")) as error:
        list(runner.stream_lines(command))

    assert error.value.stderr == "stderr boom\n"


def test_sync_cancel_pre_set_raises_cancelled_without_spawning(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = SyncCodexProcessRunner(executable_path=str(executable))

    marker = tmp_path / "sync_pre_set_marker"
    signal = threading.Event()
    signal.set()

    command = _build_command(mode="stdout_lines", signal=signal, marker=marker)

    with pytest.raises(CodexCancelledError, match="Turn cancelled"):
        list(runner.stream_lines(command))

    assert not marker.exists()


def test_sync_cancel_mid_run_terminates_and_raises_cancelled(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = SyncCodexProcessRunner(executable_path=str(executable))

    signal = threading.Event()
    command = _build_command(mode="long_running", signal=signal)

    iterator = runner.stream_lines(command)

    assert next(iterator) == "ready"

    signal.set()
    with pytest.raises(CodexCancelledError, match="Turn cancelled"):
        next(iterator)


def test_async_stream_lines_yields_stdout_lines_without_newlines(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = AsyncCodexProcessRunner(executable_path=str(executable))
    command = _build_command(mode="stdout_lines")

    async def run() -> list[str]:
        return [line async for line in runner.stream_lines(command)]

    lines = _run_async(run())

    assert lines == ["first line", "second line", "third line"]


def test_async_nonzero_exit_raises_codex_exec_error_includes_stderr(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = AsyncCodexProcessRunner(executable_path=str(executable))
    command = _build_command(mode="nonzero")

    async def run() -> None:
        async for _ in runner.stream_lines(command):
            pass

    with pytest.raises(CodexExecError, match=re.escape("Codex Exec exited with code 7")) as error:
        _run_async(run())

    assert error.value.stderr == "stderr boom\n"


def test_async_cancel_pre_set_raises_cancelled_without_spawning(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = AsyncCodexProcessRunner(executable_path=str(executable))

    marker = tmp_path / "async_pre_set_marker"
    signal = asyncio.Event()
    signal.set()

    command = _build_command(mode="stdout_lines", signal=signal, marker=marker)

    async def run() -> None:
        async for _ in runner.stream_lines(command):
            pass

    with pytest.raises(CodexCancelledError, match="Turn cancelled"):
        _run_async(run())

    assert not marker.exists()


def test_async_cancel_mid_run_terminates_and_raises_cancelled(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = AsyncCodexProcessRunner(executable_path=str(executable))

    async def run() -> None:
        signal = asyncio.Event()
        command = _build_command(mode="long_running", signal=signal)
        iterator = runner.stream_lines(command)

        assert await anext(iterator) == "ready"

        signal.set()
        with pytest.raises(CodexCancelledError, match="Turn cancelled"):
            await anext(iterator)

    _run_async(run())


def _build_command(
    *,
    mode: str,
    signal: threading.Event | asyncio.Event | None = None,
    marker: Path | None = None,
) -> CodexExecCommand:
    env = dict(os.environ)
    env["FAKE_CODEX_MODE"] = mode
    if marker is not None:
        env["FAKE_CODEX_MARKER"] = str(marker)

    return CodexExecCommand(
        argv=["exec", "--experimental-json"],
        env=env,
        stdin="ignored stdin",
        signal=signal,
    )


def _create_fake_codex_executable(tmp_path: Path) -> Path:
    target = tmp_path / "fake_codex_target.py"
    target.write_text(
        dedent(
            """\
            from __future__ import annotations

            import os
            import sys
            import time
            from pathlib import Path

            marker = os.environ.get("FAKE_CODEX_MARKER")
            if marker:
                Path(marker).write_text("invoked", encoding="utf-8")

            mode = os.environ.get("FAKE_CODEX_MODE", "stdout_lines")
            _ = sys.stdin.read()

            if mode == "stdout_lines":
                sys.stdout.write("first line\\r\\nsecond line\\nthird line\\r\\n")
                sys.stdout.flush()
                raise SystemExit(0)

            if mode == "nonzero":
                sys.stderr.write("stderr boom\\n")
                sys.stderr.flush()
                raise SystemExit(7)

            if mode == "long_running":
                sys.stdout.write("ready\\n")
                sys.stdout.flush()
                while True:
                    time.sleep(0.1)

            raise SystemExit(0)
            """,
        ),
        encoding="utf-8",
    )

    if os.name == "nt":
        executable = tmp_path / "codex.bat"
        executable.write_text(
            f'@echo off\r\n"{sys.executable}" "{target}" %*\r\n',
            encoding="utf-8",
        )
        return executable

    executable = tmp_path / "codex"
    executable.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{target}" "$@"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_async(awaitable: Coroutine[object, object, _T]) -> _T:
    return asyncio.run(awaitable)
