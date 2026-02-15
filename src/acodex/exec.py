from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import re
import shutil
import signal as signal_module
import subprocess
import threading
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, TypedDict, TypeVar

from acodex.codex_options import CodexConfigObject
from acodex.thread_options import ApprovalMode, ModelReasoningEffort, SandboxMode, WebSearchMode
from acodex.turn_options import TurnSignal

if TYPE_CHECKING:
    from typing_extensions import NotRequired


INTERNAL_ORIGINATOR_ENV = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"
PYTHON_SDK_ORIGINATOR = "codex_sdk_py"

TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

TURN_CANCELLED_MESSAGE = "Turn cancelled"

CHILD_NO_STDIN_MESSAGE = "Child process has no stdin"
CHILD_NO_STDOUT_MESSAGE = "Child process has no stdout"
CHILD_NO_STDERR_MESSAGE = "Child process has no stderr"


class CodexExecArgs(TypedDict):
    """Arguments for the exec layer.

    Set `signal` via `event.set()` to request cancellation. Use `threading.Event` in synchronous
    flows and `asyncio.Event` in asynchronous flows.
    """

    input: str
    base_url: NotRequired[str]
    api_key: NotRequired[str]
    thread_id: NotRequired[str | None]
    images: NotRequired[list[str]]
    model: NotRequired[str]
    sandbox_mode: NotRequired[SandboxMode]
    working_directory: NotRequired[str]
    additional_directories: NotRequired[list[str]]
    skip_git_repo_check: NotRequired[bool]
    output_schema_file: NotRequired[str]
    model_reasoning_effort: NotRequired[ModelReasoningEffort]
    signal: NotRequired[TurnSignal]
    network_access_enabled: NotRequired[bool]
    web_search_mode: NotRequired[WebSearchMode]
    web_search_enabled: NotRequired[bool]
    approval_policy: NotRequired[ApprovalMode]


class CodexExec:
    """Execute `codex exec` calls for the synchronous client."""

    def __init__(
        self,
        executable_path: str | None = None,
        env: dict[str, str] | None = None,
        config_overrides: CodexConfigObject | None = None,
    ) -> None:
        self._executable_path = executable_path or find_codex_path()
        self._env = env
        self._config_overrides = config_overrides

    def run(self, args: CodexExecArgs) -> Iterator[str]:
        """Run Codex and stream JSONL lines."""
        return _run_subprocess_streamed(
            executable_path=self._executable_path,
            env_override=self._env,
            config_overrides=self._config_overrides,
            args=args,
        )


class AsyncCodexExec:
    """Execute `codex exec` calls for the asynchronous client."""

    def __init__(
        self,
        executable_path: str | None = None,
        env: dict[str, str] | None = None,
        config_overrides: CodexConfigObject | None = None,
    ) -> None:
        self._executable_path = executable_path or find_codex_path()
        self._env = env
        self._config_overrides = config_overrides

    async def run(self, args: CodexExecArgs) -> AsyncIterator[str]:
        """Run Codex and stream JSONL lines asynchronously."""
        async for line in _arun_subprocess_streamed(
            executable_path=self._executable_path,
            env_override=self._env,
            config_overrides=self._config_overrides,
            args=args,
        ):
            yield line


def find_codex_path() -> str:
    resolved = shutil.which("codex")
    if resolved is None:
        message = "Unable to locate `codex`. Install it or pass codex_path_override."
        raise RuntimeError(message)
    return resolved


def serialize_config_overrides(config: CodexConfigObject) -> list[str]:
    overrides: list[str] = []
    flatten_config_overrides(config, "", overrides)
    return overrides


def flatten_config_overrides(value: object, prefix: str, out: list[str]) -> None:
    if not isinstance(value, dict):
        if prefix:
            out.append(f"{prefix}={to_toml_value(value, prefix)}")
            return
        message = "Codex config overrides must be a plain object"
        raise RuntimeError(message)

    entries = list(value.items())
    if not prefix and not entries:
        return

    if prefix and not entries:
        out.append(f"{prefix}={{}}")
        return

    for key, child in entries:
        if not isinstance(key, str) or not key:
            message = "Codex config override keys must be non-empty strings"
            raise RuntimeError(message)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            flatten_config_overrides(child, path, out)
        else:
            out.append(f"{path}={to_toml_value(child, path)}")


def to_toml_value(value: object, path: str) -> str:
    scalar = _to_toml_scalar(value, path)
    if scalar is not None:
        return scalar

    if isinstance(value, list):
        return _to_toml_array(value, path)

    if isinstance(value, dict):
        return _to_toml_inline_table(value, path)

    message = f"Unsupported Codex config override value at {path}: {type(value).__name__}"
    raise RuntimeError(message)


def _to_toml_scalar(value: object, path: str) -> str | None:
    if isinstance(value, str):
        return json.dumps(value)

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value}"

    if isinstance(value, float):
        if not math.isfinite(value):
            message = f"Codex config override at {path} must be a finite number"
            raise RuntimeError(message)
        return f"{value}"

    if value is None:
        message = f"Codex config override at {path} cannot be null"
        raise RuntimeError(message)

    return None


def _to_toml_array(value: list[object], path: str) -> str:
    rendered = [to_toml_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    return f"[{', '.join(rendered)}]"


def _to_toml_inline_table(value: dict[object, object], path: str) -> str:
    parts: list[str] = []
    for key, child in value.items():
        if not isinstance(key, str) or not key:
            message = "Codex config override keys must be non-empty strings"
            raise RuntimeError(message)
        parts.append(f"{format_toml_key(key)} = {to_toml_value(child, f'{path}.{key}')}")
    return f"{{{', '.join(parts)}}}"


def format_toml_key(key: str) -> str:
    return key if TOML_BARE_KEY.fullmatch(key) else json.dumps(key)


def _build_command_args(
    *,
    config_overrides: CodexConfigObject | None,
    args: CodexExecArgs,
) -> list[str]:
    command_args = ["exec", "--experimental-json"]

    _append_config_overrides(command_args, config_overrides)
    _append_basic_flags(command_args, args)
    _append_config_flags(command_args, args)
    _append_resume_and_images(command_args, args)

    return command_args


def _append_config_overrides(
    command_args: list[str],
    config_overrides: CodexConfigObject | None,
) -> None:
    if config_overrides is None:
        return
    for override in serialize_config_overrides(config_overrides):
        command_args.extend(["--config", override])


def _append_basic_flags(command_args: list[str], args: CodexExecArgs) -> None:
    model = args.get("model")
    if model is not None:
        command_args.extend(["--model", model])

    sandbox_mode = args.get("sandbox_mode")
    if sandbox_mode is not None:
        command_args.extend(["--sandbox", sandbox_mode])

    working_directory = args.get("working_directory")
    if working_directory is not None:
        command_args.extend(["--cd", working_directory])

    additional_directories = args.get("additional_directories")
    if additional_directories:
        for directory in additional_directories:
            command_args.extend(["--add-dir", directory])

    if args.get("skip_git_repo_check"):
        command_args.append("--skip-git-repo-check")

    output_schema_file = args.get("output_schema_file")
    if output_schema_file is not None:
        command_args.extend(["--output-schema", output_schema_file])


def _append_config_flags(command_args: list[str], args: CodexExecArgs) -> None:
    model_reasoning_effort = args.get("model_reasoning_effort")
    if model_reasoning_effort is not None:
        command_args.extend(
            ["--config", f"model_reasoning_effort={json.dumps(model_reasoning_effort)}"],
        )

    network_access_enabled = args.get("network_access_enabled")
    if network_access_enabled is not None:
        network_literal = "true" if network_access_enabled else "false"
        command_args.extend(
            ["--config", f"sandbox_workspace_write.network_access={network_literal}"],
        )

    web_search_mode = args.get("web_search_mode")
    web_search_enabled = args.get("web_search_enabled")
    if web_search_mode is not None:
        command_args.extend(["--config", f"web_search={json.dumps(web_search_mode)}"])
    elif web_search_enabled is True:
        command_args.extend(["--config", 'web_search="live"'])
    elif web_search_enabled is False:
        command_args.extend(["--config", 'web_search="disabled"'])

    approval_policy = args.get("approval_policy")
    if approval_policy is not None:
        command_args.extend(["--config", f"approval_policy={json.dumps(approval_policy)}"])


def _append_resume_and_images(command_args: list[str], args: CodexExecArgs) -> None:
    thread_id = args.get("thread_id")
    if isinstance(thread_id, str) and thread_id:
        command_args.extend(["resume", thread_id])

    images = args.get("images")
    if images:
        for image in images:
            command_args.extend(["--image", image])


def _build_env(
    *,
    env_override: dict[str, str] | None,
    base_url: str | None,
    api_key: str | None,
) -> dict[str, str]:
    env = dict(env_override) if env_override is not None else dict(os.environ)

    if INTERNAL_ORIGINATOR_ENV not in env:
        env[INTERNAL_ORIGINATOR_ENV] = PYTHON_SDK_ORIGINATOR
    if base_url is not None:
        env["OPENAI_BASE_URL"] = base_url
    if api_key is not None:
        env["CODEX_API_KEY"] = api_key

    return env


def _format_exit_detail(returncode: int) -> str:
    if returncode < 0:
        signum = -returncode
        try:
            return f"signal {signal_module.Signals(signum).name}"
        except ValueError:
            return f"signal {signum}"
    return f"code {returncode}"


def _validate_sync_turn_signal(signal: TurnSignal | None) -> threading.Event | None:
    if signal is None:
        return None
    if not isinstance(signal, threading.Event):
        message = "signal must be a threading.Event for synchronous runs"
        raise TypeError(message)
    if signal.is_set():
        message = TURN_CANCELLED_MESSAGE
        raise RuntimeError(message)
    return signal


def _terminate_sync_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    with contextlib.suppress(OSError):
        proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            proc.kill()


def _close_pipes(proc: subprocess.Popen[str]) -> None:
    for pipe in (proc.stdin, proc.stdout, proc.stderr):
        if pipe is not None:
            with contextlib.suppress(OSError, ValueError):
                pipe.close()


def _spawn_sync_process(
    executable_path: str,
    command_args: list[str],
    env: dict[str, str],
) -> subprocess.Popen[str]:
    # This is the core responsibility of this SDK: spawning the Codex CLI.
    return subprocess.Popen(  # noqa: S603
        [executable_path, *command_args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


_PipeT = TypeVar("_PipeT")


def _require_pipe(pipe: _PipeT | None, missing_message: str) -> _PipeT:
    if pipe is None:
        raise RuntimeError(missing_message)
    return pipe


def _write_sync_stdin(proc: subprocess.Popen[str], input_text: str) -> None:
    stdin = _require_pipe(proc.stdin, CHILD_NO_STDIN_MESSAGE)
    stdin.write(input_text)
    stdin.close()


def _start_stderr_reader(
    proc: subprocess.Popen[str],
    stderr_chunks: list[str],
) -> threading.Thread:
    stderr = _require_pipe(proc.stderr, CHILD_NO_STDERR_MESSAGE)

    def _read() -> None:
        try:
            while True:
                chunk = stderr.read(4096)
                if not chunk:
                    break
                stderr_chunks.append(chunk)
        except (OSError, ValueError):
            return

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    return thread


def _start_cancel_watcher(
    turn_signal: threading.Event | None,
    cancel_requested: threading.Event,
    proc: subprocess.Popen[str],
) -> threading.Thread | None:
    if turn_signal is None:
        return None

    def _watch() -> None:
        turn_signal.wait()
        cancel_requested.set()
        _terminate_sync_process(proc)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return thread


def _raise_for_nonzero_exit(returncode: int, stderr_text: str) -> None:
    if returncode == 0:
        return
    message = f"Codex Exec exited with {_format_exit_detail(returncode)}: {stderr_text}"
    raise RuntimeError(message)


def _run_subprocess_streamed(
    *,
    executable_path: str,
    env_override: dict[str, str] | None,
    config_overrides: CodexConfigObject | None,
    args: CodexExecArgs,
) -> Iterator[str]:
    turn_signal = _validate_sync_turn_signal(args.get("signal"))

    command_args = _build_command_args(config_overrides=config_overrides, args=args)
    env = _build_env(
        env_override=env_override,
        base_url=args.get("base_url"),
        api_key=args.get("api_key"),
    )

    cancel_requested = threading.Event()
    stderr_chunks: list[str] = []
    proc: subprocess.Popen[str] | None = None
    stderr_thread: threading.Thread | None = None
    cancel_thread: threading.Thread | None = None

    try:
        proc = _spawn_sync_process(executable_path, command_args, env)
        stderr_thread = _start_stderr_reader(proc, stderr_chunks)
        cancel_thread = _start_cancel_watcher(turn_signal, cancel_requested, proc)

        _write_sync_stdin(proc, args["input"])

        stdout = _require_pipe(proc.stdout, CHILD_NO_STDOUT_MESSAGE)
        for raw_line in stdout:
            if cancel_requested.is_set():
                break
            yield raw_line.rstrip("\r\n")

        returncode = proc.wait()
        if cancel_requested.is_set():
            message = TURN_CANCELLED_MESSAGE
            raise RuntimeError(message)

        stderr_text = "".join(stderr_chunks)
        _raise_for_nonzero_exit(returncode, stderr_text)
    finally:
        if proc is not None:
            _terminate_sync_process(proc)
            _close_pipes(proc)
        if cancel_thread is not None:
            cancel_thread.join(timeout=0.2)
        if stderr_thread is not None:
            stderr_thread.join(timeout=0.2)


async def _arun_subprocess_streamed(
    *,
    executable_path: str,
    env_override: dict[str, str] | None,
    config_overrides: CodexConfigObject | None,
    args: CodexExecArgs,
) -> AsyncIterator[str]:
    turn_signal = args.get("signal")
    if turn_signal is not None and _signal_is_set(turn_signal):
        message = TURN_CANCELLED_MESSAGE
        raise RuntimeError(message)

    command_args = _build_command_args(config_overrides=config_overrides, args=args)
    env = _build_env(
        env_override=env_override,
        base_url=args.get("base_url"),
        api_key=args.get("api_key"),
    )

    proc = await _spawn_async_process(executable_path, command_args, env)
    signal_task = _start_async_signal_task(turn_signal)
    stderr_task = asyncio.create_task(_require_pipe(proc.stderr, CHILD_NO_STDERR_MESSAGE).read())

    try:
        await _write_async_stdin(proc, args["input"])
        stdout = _require_pipe(proc.stdout, CHILD_NO_STDOUT_MESSAGE)
        async for line in _astream_stdout(stdout, proc, signal_task):
            yield line

        returncode = await proc.wait()
        stderr_text = (await stderr_task).decode("utf-8", errors="replace")
        _raise_for_nonzero_exit(returncode, stderr_text)
    finally:
        if signal_task is not None:
            signal_task.cancel()
        await _terminate_async_process(proc)
        with contextlib.suppress(OSError, RuntimeError):
            await stderr_task


async def _spawn_async_process(
    executable_path: str,
    command_args: list[str],
    env: dict[str, str],
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        executable_path,
        *command_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )


async def _terminate_async_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()


def _start_async_signal_task(turn_signal: TurnSignal | None) -> asyncio.Task[object] | None:
    if turn_signal is None:
        return None
    if isinstance(turn_signal, asyncio.Event):
        return asyncio.create_task(turn_signal.wait())
    return asyncio.create_task(asyncio.to_thread(turn_signal.wait))


async def _write_async_stdin(proc: asyncio.subprocess.Process, input_text: str) -> None:
    stdin = _require_pipe(proc.stdin, CHILD_NO_STDIN_MESSAGE)
    stdin.write(input_text.encode("utf-8"))
    await stdin.drain()
    stdin.close()
    if hasattr(stdin, "wait_closed"):
        await stdin.wait_closed()  # type: ignore[func-returns-value]


async def _astream_stdout(
    stdout: asyncio.StreamReader,
    proc: asyncio.subprocess.Process,
    signal_task: asyncio.Task[object] | None,
) -> AsyncIterator[str]:
    while True:
        line_task: asyncio.Task[bytes] = asyncio.create_task(stdout.readline())
        tasks: set[asyncio.Task[object]] = {line_task}
        if signal_task is not None:
            tasks.add(signal_task)

        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if signal_task is not None and signal_task in done:
            line_task.cancel()
            await _terminate_async_process(proc)
            message = TURN_CANCELLED_MESSAGE
            raise RuntimeError(message)

        raw_line = line_task.result()
        if not raw_line:
            return
        yield raw_line.decode("utf-8", errors="replace").rstrip("\r\n")


def _signal_is_set(signal: object) -> bool:
    if isinstance(signal, threading.Event):
        return signal.is_set()
    if isinstance(signal, asyncio.Event):
        return signal.is_set()
    message = "signal must be a threading.Event or asyncio.Event"
    raise TypeError(message)
