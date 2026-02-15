from __future__ import annotations

import asyncio
import queue
import subprocess  # noqa: S404
import threading
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from dataclasses import dataclass
from typing import IO, Final, NamedTuple, NoReturn, TypeAlias, cast

from acodex._internal.exec import CodexExecCommand
from acodex.exceptions import CodexCancelledError, CodexExecError

_READ_POLL_INTERVAL_SECONDS: Final[float] = 0.05
_PROCESS_TERMINATE_TIMEOUT_SECONDS: Final[float] = 1.0


class _StdoutEofSentinel:
    pass


class _AsyncTimeoutSentinel:
    pass


class _AsyncCancelledSentinel:
    pass


_STDOUT_EOF: Final[_StdoutEofSentinel] = _StdoutEofSentinel()
_ASYNC_TIMEOUT: Final[_AsyncTimeoutSentinel] = _AsyncTimeoutSentinel()
_ASYNC_CANCELLED: Final[_AsyncCancelledSentinel] = _AsyncCancelledSentinel()

_StdoutQueueItem: TypeAlias = str | _StdoutEofSentinel
_AsyncReadResult: TypeAlias = bytes | _AsyncTimeoutSentinel | _AsyncCancelledSentinel


@dataclass(frozen=True, slots=True)
class _SyncResources:
    stdin: IO[str]
    stdout: IO[str]
    stderr: IO[str]
    stdout_thread: threading.Thread
    stderr_thread: threading.Thread


class _SyncStdio(NamedTuple):
    stdin: IO[str]
    stdout: IO[str]
    stderr: IO[str]


class _SyncReaderThreads(NamedTuple):
    stdout_thread: threading.Thread
    stderr_thread: threading.Thread


class _AsyncStdio(NamedTuple):
    stdin: asyncio.StreamWriter
    stdout: asyncio.StreamReader
    stderr: asyncio.StreamReader


class CodexProcessRunnerBase(ABC):
    def __init__(self, *, executable_path: str) -> None:
        self._executable_path: Final[str] = executable_path

    @staticmethod
    def _check_cancelled(command: CodexExecCommand) -> None:
        signal = command.signal
        if signal is None:
            return

        if signal.is_set():
            raise CodexCancelledError("Turn cancelled")

    @staticmethod
    def _raise_exec_error(*, detail: str, stderr: str) -> NoReturn:
        raise CodexExecError(f"Codex Exec exited with {detail}", stderr=stderr)

    @abstractmethod
    def stream_lines(self, command: CodexExecCommand) -> Iterator[str] | AsyncIterator[str]:
        """Run command and stream stdout lines."""


class SyncCodexProcessRunner(CodexProcessRunnerBase):
    def stream_lines(self, command: CodexExecCommand) -> Iterator[str]:
        self._check_cancelled(command)

        process = self._spawn_process(command)
        stdio = self._require_stdio(process)

        stdout_queue: queue.Queue[_StdoutQueueItem] = queue.Queue()
        stderr_chunks: list[str] = []
        reader_threads = self._start_reader_threads(
            stdout=stdio.stdout,
            stderr=stdio.stderr,
            stdout_queue=stdout_queue,
            stderr_chunks=stderr_chunks,
        )
        resources = _SyncResources(
            stdin=stdio.stdin,
            stdout=stdio.stdout,
            stderr=stdio.stderr,
            stdout_thread=reader_threads.stdout_thread,
            stderr_thread=reader_threads.stderr_thread,
        )

        try:
            self._write_stdin(stdin=stdio.stdin, stdin_text=command.stdin)
            yield from self._iter_stdout_lines(
                process=process,
                command=command,
                stdout_queue=stdout_queue,
                stdout_thread=reader_threads.stdout_thread,
            )
            return_code = process.wait()
            reader_threads.stderr_thread.join()
            stderr_text = "".join(stderr_chunks)
            self._raise_on_bad_exit(return_code=return_code, stderr=stderr_text)
        except CodexCancelledError:
            self._terminate_process(process)
            raise
        finally:
            self._cleanup(process=process, resources=resources)

    def _spawn_process(self, command: CodexExecCommand) -> subprocess.Popen[str]:
        try:
            return subprocess.Popen(  # noqa: S603
                [self._executable_path, *command.argv],
                env=command.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as error:
            self._raise_exec_error(detail=f"spawn failure: {error}", stderr="")

    def _require_stdio(self, process: subprocess.Popen[str]) -> _SyncStdio:
        stdin = process.stdin
        stdout = process.stdout
        stderr = process.stderr
        if stdin is None or stdout is None or stderr is None:
            self._terminate_process(process)
            self._raise_exec_error(detail="spawn failure: missing stdio streams", stderr="")

        return _SyncStdio(stdin=stdin, stdout=stdout, stderr=stderr)

    def _start_reader_threads(
        self,
        *,
        stdout: IO[str],
        stderr: IO[str],
        stdout_queue: queue.Queue[_StdoutQueueItem],
        stderr_chunks: list[str],
    ) -> _SyncReaderThreads:
        stdout_thread = threading.Thread(
            target=self._pump_stdout,
            args=(stdout, stdout_queue),
            name="acodex-sync-stdout-reader",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._pump_stderr,
            args=(stderr, stderr_chunks),
            name="acodex-sync-stderr-reader",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        return _SyncReaderThreads(stdout_thread=stdout_thread, stderr_thread=stderr_thread)

    @staticmethod
    def _write_stdin(*, stdin: IO[str], stdin_text: str) -> None:
        with suppress(BrokenPipeError, OSError):
            stdin.write(stdin_text)
            stdin.flush()
        with suppress(OSError):
            stdin.close()

    def _iter_stdout_lines(
        self,
        *,
        process: subprocess.Popen[str],
        command: CodexExecCommand,
        stdout_queue: queue.Queue[_StdoutQueueItem],
        stdout_thread: threading.Thread,
    ) -> Iterator[str]:
        while True:
            self._check_cancelled(command)

            try:
                item = stdout_queue.get(timeout=_READ_POLL_INTERVAL_SECONDS)
            except queue.Empty:
                if process.poll() is not None and not stdout_thread.is_alive():
                    return
                continue

            if item is _STDOUT_EOF:
                return

            yield cast("str", item).rstrip("\r\n")

    @classmethod
    def _raise_on_bad_exit(cls, *, return_code: int, stderr: str) -> None:
        if return_code != 0:
            cls._raise_exec_error(detail=f"code {return_code}", stderr=stderr)

    def _cleanup(self, *, process: subprocess.Popen[str], resources: _SyncResources) -> None:
        self._terminate_process(process)
        with suppress(OSError):
            resources.stdin.close()
        with suppress(OSError):
            resources.stdout.close()
        with suppress(OSError):
            resources.stderr.close()
        resources.stdout_thread.join()
        resources.stderr_thread.join()

    @staticmethod
    def _pump_stdout(stream: IO[str], output: queue.Queue[_StdoutQueueItem]) -> None:
        try:
            for line in stream:
                output.put(line)
        finally:
            output.put(_STDOUT_EOF)

    @staticmethod
    def _pump_stderr(stream: IO[str], chunks: list[str]) -> None:
        chunks.append(stream.read())

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return

        with suppress(OSError):
            process.terminate()

        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=_PROCESS_TERMINATE_TIMEOUT_SECONDS)

        if process.poll() is not None:
            return

        with suppress(OSError):
            process.kill()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=_PROCESS_TERMINATE_TIMEOUT_SECONDS)


class AsyncCodexProcessRunner(CodexProcessRunnerBase):
    async def stream_lines(self, command: CodexExecCommand) -> AsyncIterator[str]:
        self._check_cancelled(command)

        process = await self._spawn_process(command)
        stdio = self._require_stdio(process)
        stderr_task = asyncio.create_task(
            stdio.stderr.read(),
            name="acodex-async-stderr-reader",
        )

        try:
            await self._write_stdin(stdin=stdio.stdin, stdin_text=command.stdin)
            async for line in self._iter_stdout_lines(command=command, stdout=stdio.stdout):
                yield line
            return_code = await process.wait()
            stderr_text = await self._decode_stderr(stderr_task)
            self._raise_on_bad_exit(return_code=return_code, stderr=stderr_text)
        except CodexCancelledError:
            await self._terminate_process(process)
            raise
        finally:
            await self._cleanup(
                process=process,
                stdin=stdio.stdin,
                stderr_task=stderr_task,
            )

    async def _spawn_process(self, command: CodexExecCommand) -> asyncio.subprocess.Process:
        try:
            return await asyncio.create_subprocess_exec(
                self._executable_path,
                *command.argv,
                env=command.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            self._raise_exec_error(detail=f"spawn failure: {error}", stderr="")

    async def _cleanup(
        self,
        *,
        process: asyncio.subprocess.Process,
        stdin: asyncio.StreamWriter,
        stderr_task: asyncio.Task[bytes],
    ) -> None:
        await self._terminate_process(process)
        if not stdin.is_closing():
            stdin.close()
        with suppress(BrokenPipeError, ConnectionResetError):
            await stdin.wait_closed()
        if not stderr_task.done():
            stderr_task.cancel()
        with suppress(asyncio.CancelledError):
            await stderr_task

    @staticmethod
    def _require_stdio(
        process: asyncio.subprocess.Process,
    ) -> _AsyncStdio:
        stdin = process.stdin
        stdout = process.stdout
        stderr = process.stderr
        if stdin is None or stdout is None or stderr is None:
            raise CodexExecError(
                "Codex Exec exited with spawn failure: missing stdio streams",
                stderr="",
            )

        return _AsyncStdio(stdin=stdin, stdout=stdout, stderr=stderr)

    @staticmethod
    async def _write_stdin(*, stdin: asyncio.StreamWriter, stdin_text: str) -> None:
        with suppress(BrokenPipeError, ConnectionResetError):
            stdin.write(stdin_text.encode("utf-8"))
            await stdin.drain()
        stdin.close()
        with suppress(BrokenPipeError, ConnectionResetError):
            await stdin.wait_closed()

    async def _iter_stdout_lines(
        self,
        *,
        command: CodexExecCommand,
        stdout: asyncio.StreamReader,
    ) -> AsyncIterator[str]:
        while True:
            self._check_cancelled(command)

            line = await self._read_next_line(command=command, stdout=stdout)
            if line is _ASYNC_TIMEOUT:
                continue
            if line is _ASYNC_CANCELLED:
                self._raise_cancelled()
            if line == b"":
                return

            yield cast("bytes", line).decode("utf-8", errors="replace").rstrip("\r\n")

    @staticmethod
    async def _read_next_line(
        *,
        command: CodexExecCommand,
        stdout: asyncio.StreamReader,
    ) -> _AsyncReadResult:
        signal = command.signal
        if isinstance(signal, asyncio.Event):
            readline_task = asyncio.create_task(
                stdout.readline(),
                name="acodex-async-stdout-readline",
            )
            cancelled_task = asyncio.create_task(
                signal.wait(),
                name="acodex-async-cancel-wait",
            )
            done, pending = await asyncio.wait(
                {readline_task, cancelled_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            if cancelled_task in done:
                return _ASYNC_CANCELLED

            return readline_task.result()

        try:
            return await asyncio.wait_for(
                stdout.readline(),
                timeout=_READ_POLL_INTERVAL_SECONDS,
            )
        except TimeoutError:
            return _ASYNC_TIMEOUT

    @staticmethod
    def _raise_cancelled() -> None:
        raise CodexCancelledError("Turn cancelled")

    @classmethod
    def _raise_on_bad_exit(cls, *, return_code: int, stderr: str) -> None:
        if return_code != 0:
            cls._raise_exec_error(detail=f"code {return_code}", stderr=stderr)

    @staticmethod
    async def _decode_stderr(stderr_task: asyncio.Task[bytes]) -> str:
        return (await stderr_task).decode("utf-8", errors="replace")

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return

        with suppress(ProcessLookupError):
            process.terminate()

        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_SECONDS)

        with suppress(ProcessLookupError):
            process.kill()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_SECONDS)
