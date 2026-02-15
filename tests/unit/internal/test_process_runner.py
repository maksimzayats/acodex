from __future__ import annotations

import asyncio
import os
import queue
import re
import subprocess  # noqa: S404
import sys
import threading
from collections.abc import Coroutine
from pathlib import Path
from textwrap import dedent
from typing import Any, TypeVar, cast

import pytest

from acodex._internal.exec import CodexExecCommand
from acodex._internal.process_runner import (
    _ASYNC_CANCELLED,
    AsyncCodexProcessRunner,
    SyncCodexProcessRunner,
)
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


def test_sync_nonzero_exit_before_stdout_closes_raises_codex_exec_error(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = SyncCodexProcessRunner(executable_path=str(executable))
    command = _build_command(mode="exit_before_stdout_closes")

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


def test_sync_spawn_oserror_raises_codex_exec_error() -> None:
    runner = SyncCodexProcessRunner(executable_path="codex")
    command = _build_command(mode="stdout_lines")

    def raise_oserror(*_: object, **__: object) -> None:
        raise OSError("nope")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(subprocess, "Popen", raise_oserror)
        with pytest.raises(CodexExecError, match=re.escape("spawn failure: nope")):
            list(runner.stream_lines(command))


def test_sync_missing_stdio_streams_terminates_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = SyncCodexProcessRunner(executable_path="codex")
    command = _build_command(mode="stdout_lines")
    process = _MissingSyncStdioProcess()
    terminated: list[object] = []

    def fake_spawn(_: object) -> _MissingSyncStdioProcess:
        return process

    def fake_terminate(proc: object) -> None:
        terminated.append(proc)

    monkeypatch.setattr(runner, "_spawn_process", fake_spawn)
    monkeypatch.setattr(runner, "_terminate_process", fake_terminate)

    with pytest.raises(CodexExecError, match="spawn failure: missing stdio streams"):
        list(runner.stream_lines(command))

    assert terminated == [process]


def test_sync_stream_lines_handles_poll_timeouts_before_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = SyncCodexProcessRunner(executable_path="codex")
    command = CodexExecCommand(argv=[], env={}, stdin="")
    stdout_queue: queue.Queue[Any] = queue.Queue()
    process = _PolledSyncProcess(return_code=0)
    stdout_thread = threading.Thread()

    monkeypatch.setattr("acodex._internal.process_runner._READ_POLL_INTERVAL_SECONDS", 0.001)

    lines = list(
        runner._iter_stdout_lines(
            process=cast("subprocess.Popen[str]", process),
            command=command,
            stdout_queue=cast("Any", stdout_queue),
            stdout_thread=stdout_thread,
        ),
    )

    assert lines == []


def test_sync_terminate_process_falls_back_to_kill_after_timeouts() -> None:
    process = _KillFallbackSyncProcess()

    SyncCodexProcessRunner._terminate_process(cast("subprocess.Popen[str]", process))

    assert process.kill_called


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


def test_async_nonzero_exit_before_stdout_closes_raises_codex_exec_error(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = AsyncCodexProcessRunner(executable_path=str(executable))
    command = _build_command(mode="exit_before_stdout_closes")

    async def run() -> None:
        async for _ in runner.stream_lines(command):
            pass

    with pytest.raises(CodexExecError, match=re.escape("Codex Exec exited with code 7")) as error:
        _run_async(asyncio.wait_for(run(), timeout=2.0))

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


def test_async_spawn_oserror_raises_codex_exec_error() -> None:
    runner = AsyncCodexProcessRunner(executable_path="codex")
    command = _build_command(mode="stdout_lines")

    async def raise_oserror(*_: object, **__: object) -> asyncio.subprocess.Process:
        await asyncio.sleep(0)
        raise OSError("nope")

    async def run() -> None:
        async for _ in runner.stream_lines(command):
            pass

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(asyncio, "create_subprocess_exec", raise_oserror)
        with pytest.raises(CodexExecError, match=re.escape("spawn failure: nope")):
            _run_async(run())


def test_async_require_stdio_raises_when_streams_missing() -> None:
    process = _MissingAsyncStdioProcess()

    with pytest.raises(CodexExecError, match="spawn failure: missing stdio streams"):
        AsyncCodexProcessRunner._require_stdio(cast("asyncio.subprocess.Process", process))


def test_async_cancel_during_readline_uses_async_event_wait_path(tmp_path: Path) -> None:
    executable = _create_fake_codex_executable(tmp_path)
    runner = AsyncCodexProcessRunner(executable_path=str(executable))

    async def run() -> None:
        signal = asyncio.Event()
        command = _build_command(mode="long_running", signal=signal)
        iterator = runner.stream_lines(command)

        assert await anext(iterator) == "ready"

        async def read_next() -> str:
            return await anext(iterator)

        next_task: asyncio.Task[str] = asyncio.create_task(read_next())
        await asyncio.sleep(0.01)
        assert not next_task.done()

        signal.set()
        with pytest.raises(CodexCancelledError, match="Turn cancelled"):
            await next_task

    _run_async(run())


def test_async_read_timeout_path_returns_timeout_then_eventually_yields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = AsyncCodexProcessRunner(executable_path="codex")
    command = CodexExecCommand(argv=[], env={}, stdin="", signal=threading.Event())
    stdout = _DelayedAsyncStdout()

    async def run() -> list[str]:
        return [
            line
            async for line in runner._iter_stdout_lines(
                command=command,
                stdout=cast("asyncio.StreamReader", stdout),
            )
        ]

    monkeypatch.setattr("acodex._internal.process_runner._READ_POLL_INTERVAL_SECONDS", 0.001)
    lines = _run_async(run())

    assert lines == ["eventual line"]


def test_async_cleanup_closes_stdin_and_cancels_stderr_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = AsyncCodexProcessRunner(executable_path="codex")
    stdin = _FakeAsyncStdin()
    stderr_task: asyncio.Task[bytes] | None = None

    async def fake_terminate(_: object) -> None:
        await asyncio.sleep(0)

    async def run() -> None:
        nonlocal stderr_task
        stderr_task = asyncio.create_task(asyncio.sleep(10.0, result=b"stderr"))
        monkeypatch.setattr(runner, "_terminate_process", fake_terminate)
        await runner._cleanup(
            process=cast("asyncio.subprocess.Process", _FakeAsyncProcess()),
            stdin=cast("asyncio.StreamWriter", stdin),
            stderr_task=stderr_task,
        )

    _run_async(run())

    assert stdin.close_called
    assert stderr_task is not None
    assert stderr_task.cancelled()


def test_async_read_next_line_returns_cancelled_when_signal_task_finishes_first() -> None:
    runner = AsyncCodexProcessRunner(executable_path="codex")
    signal = asyncio.Event()
    signal.set()
    command = CodexExecCommand(argv=[], env={}, stdin="", signal=signal)
    stdout = _ImmediateAsyncStdout()

    result = _run_async(
        runner._read_next_line(command=command, stdout=cast("asyncio.StreamReader", stdout)),
    )

    assert result is _ASYNC_CANCELLED


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
            import subprocess
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

            if mode == "exit_before_stdout_closes":
                # Keep stdout alive briefly after parent exit to mirror TS parity race.
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        "import sys, time; time.sleep(0.05); sys.stdout.write('late line\\\\n'); sys.stdout.flush()",
                    ],
                    stdin=subprocess.DEVNULL,
                )
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


class _MissingSyncStdioProcess:
    stdin: None = None
    stdout: None = None
    stderr: None = None


class _PolledSyncProcess:
    def __init__(self, *, return_code: int) -> None:
        self._return_code = return_code

    def poll(self) -> int:
        return self._return_code


class _KillFallbackSyncProcess:
    def __init__(self) -> None:
        self.kill_called = False
        self.terminate_called = False

    def poll(self) -> int | None:
        if self.kill_called:
            return 0
        return None

    def terminate(self) -> None:
        self.terminate_called = True

    def wait(self, timeout: float | None = None) -> int:
        if not self.kill_called:
            raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout or 1.0)
        return 0

    def kill(self) -> None:
        self.kill_called = True


class _MissingAsyncStdioProcess:
    stdin: None = None
    stdout: None = None
    stderr: None = None


class _FakeAsyncProcess:
    returncode = 0


class _FakeAsyncStdin:
    def __init__(self) -> None:
        self.close_called = False

    def is_closing(self) -> bool:
        return self.close_called

    def close(self) -> None:
        self.close_called = True

    async def wait_closed(self) -> None:
        _ = self.close_called


class _DelayedAsyncStdout:
    def __init__(self) -> None:
        self._read_calls = 0

    async def readline(self) -> bytes:
        self._read_calls += 1
        if self._read_calls == 1:
            await asyncio.sleep(0.01)
            return b"delayed line\n"
        if self._read_calls == 2:
            return b"eventual line\n"
        return b""


class _ImmediateAsyncStdout:
    def __init__(self) -> None:
        self._read_calls = 0

    async def readline(self) -> bytes:
        self._read_calls += 1
        return b"ready\n"


def _run_async(awaitable: Coroutine[object, object, _T]) -> _T:
    return asyncio.run(awaitable)
