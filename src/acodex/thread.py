from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import NamedTuple, cast

from typing_extensions import Unpack

from acodex._internal.exec import CodexExecArgs
from acodex._internal.output_schema_file import UNSET, create_output_schema_file
from acodex._internal.thread_core import (
    build_turn_or_raise,
    initial_turn_state,
    normalize_input,
    parse_thread_event_jsonl,
    reduce_turn_state,
)
from acodex.exec import AsyncCodexExec, CodexExec
from acodex.types.codex_options import CodexOptions
from acodex.types.events import ThreadEvent, ThreadStartedEvent
from acodex.types.input import Input
from acodex.types.thread_options import ThreadOptions
from acodex.types.turn import (
    AsyncRunStreamedResult,
    RunResult,
    RunStreamedResult,
    StreamedTurn,
)
from acodex.types.turn_options import TurnOptions


class Thread:
    """Represent a thread of conversation with the agent.

    One thread can have multiple consecutive turns.
    """

    def __init__(
        self,
        *,
        exec: CodexExec,  # noqa: A002
        options: CodexOptions,
        thread_options: ThreadOptions,
        thread_id: str | None = None,
    ) -> None:
        self._exec = exec
        self._options = options
        self._id = thread_id
        self._thread_options = thread_options

    @property
    def id(self) -> str | None:
        """Return the ID of the thread.

        The ID is populated after the first turn starts.
        """
        return self._id

    def run_streamed(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunStreamedResult:
        """Provide input to the agent and stream turn events as they are produced.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.

        Returns:
            A streamed turn result with an iterator of parsed events.

        """

        def event_generator() -> Iterator[ThreadEvent]:
            schema_file = create_output_schema_file(turn_options.get("output_schema", UNSET))
            line_stream: Iterator[str] | None = None
            try:
                exec_args = _build_exec_args(
                    input=input,
                    config=_ExecArgsConfig(
                        options=self._options,
                        thread_options=self._thread_options,
                        thread_id=self._id,
                    ),
                    turn_options=turn_options,
                    output_schema_path=schema_file.schema_path,
                )

                line_stream = self._exec.run(exec_args)
                for line in line_stream:
                    event = parse_thread_event_jsonl(line)
                    if event is None:
                        continue

                    if isinstance(event, ThreadStartedEvent):
                        self._id = event.thread_id

                    yield event
            finally:
                if line_stream is not None:
                    _close_if_possible(line_stream)
                schema_file.cleanup()

        return StreamedTurn(events=event_generator())

    def run(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.

        Returns:
            The completed turn with reduced items, final response, and usage.

        """
        events = self.run_streamed(input, **turn_options).events
        state = initial_turn_state()
        try:
            for event in events:
                state = reduce_turn_state(state, event)
                if state.failure_message is not None:
                    break
        finally:
            _close_if_possible(events)

        return build_turn_or_raise(state)


class AsyncThread:
    """Represent a thread of conversation with the agent.

    One thread can have multiple consecutive turns.
    """

    def __init__(
        self,
        *,
        exec: AsyncCodexExec,  # noqa: A002
        options: CodexOptions,
        thread_options: ThreadOptions,
        thread_id: str | None = None,
    ) -> None:
        self._exec = exec
        self._options = options
        self._id = thread_id
        self._thread_options = thread_options

    @property
    def id(self) -> str | None:
        """Return the ID of the thread.

        The ID is populated after the first turn starts.
        """
        return self._id

    async def run_streamed(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> AsyncRunStreamedResult:
        """Provide input to the agent and stream turn events as they are produced.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.

        Returns:
            A streamed turn result with an async iterator of parsed events.

        """

        async def event_generator() -> AsyncIterator[ThreadEvent]:
            schema_file = create_output_schema_file(turn_options.get("output_schema", UNSET))
            line_stream: AsyncIterator[str] | None = None
            try:
                exec_args = _build_exec_args(
                    input=input,
                    config=_ExecArgsConfig(
                        options=self._options,
                        thread_options=self._thread_options,
                        thread_id=self._id,
                    ),
                    turn_options=turn_options,
                    output_schema_path=schema_file.schema_path,
                )

                line_stream = self._exec.run(exec_args)
                async for line in line_stream:
                    event = parse_thread_event_jsonl(line)
                    if event is None:
                        continue

                    if isinstance(event, ThreadStartedEvent):
                        self._id = event.thread_id

                    yield event
            finally:
                if line_stream is not None:
                    await _aclose_if_possible(line_stream)
                schema_file.cleanup()

        return StreamedTurn(events=event_generator())

    async def run(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.

        Returns:
            The completed turn with reduced items, final response, and usage.

        """
        events = (await self.run_streamed(input, **turn_options)).events
        state = initial_turn_state()
        try:
            async for event in events:
                state = reduce_turn_state(state, event)
                if state.failure_message is not None:
                    break
        finally:
            await _aclose_if_possible(events)

        return build_turn_or_raise(state)


class _ExecArgsConfig(NamedTuple):
    options: CodexOptions
    thread_options: ThreadOptions
    thread_id: str | None


def _build_exec_args(
    *,
    input: Input,  # noqa: A002
    config: _ExecArgsConfig,
    turn_options: TurnOptions,
    output_schema_path: str | None,
) -> CodexExecArgs:
    normalized = normalize_input(input)
    raw_args: dict[str, object] = {
        "input": normalized.prompt,
        "thread_id": config.thread_id,
        "images": normalized.images,
    }
    _set_if_present(raw_args, key="base_url", value=config.options.get("base_url"))
    _set_if_present(raw_args, key="api_key", value=config.options.get("api_key"))

    _set_if_present(raw_args, key="model", value=config.thread_options.get("model"))
    _set_if_present(
        raw_args,
        key="sandbox_mode",
        value=config.thread_options.get("sandbox_mode"),
    )
    _set_if_present(
        raw_args,
        key="working_directory",
        value=config.thread_options.get("working_directory"),
    )
    _set_if_present(
        raw_args,
        key="additional_directories",
        value=config.thread_options.get("additional_directories"),
    )
    if config.thread_options.get("skip_git_repo_check") is True:
        raw_args["skip_git_repo_check"] = True
    _set_if_present(
        raw_args,
        key="model_reasoning_effort",
        value=config.thread_options.get("model_reasoning_effort"),
    )
    _set_if_present(
        raw_args,
        key="network_access_enabled",
        value=config.thread_options.get("network_access_enabled"),
    )
    _set_if_present(
        raw_args,
        key="web_search_mode",
        value=config.thread_options.get("web_search_mode"),
    )
    _set_if_present(
        raw_args,
        key="web_search_enabled",
        value=config.thread_options.get("web_search_enabled"),
    )
    _set_if_present(
        raw_args,
        key="approval_policy",
        value=config.thread_options.get("approval_policy"),
    )

    _set_if_present(raw_args, key="signal", value=turn_options.get("signal"))
    _set_if_present(raw_args, key="output_schema_file", value=output_schema_path)

    return cast("CodexExecArgs", raw_args)


def _set_if_present(args: dict[str, object], *, key: str, value: object) -> None:
    if value is not None:
        args[key] = value


def _close_if_possible(iterator: object) -> None:
    close_method = getattr(iterator, "close", None)
    if close_method is None:
        return
    cast("Callable[[], None]", close_method)()


async def _aclose_if_possible(iterator: object) -> None:
    close_method = getattr(iterator, "aclose", None)
    if close_method is None:
        return
    await cast("Callable[[], Awaitable[None]]", close_method)()
