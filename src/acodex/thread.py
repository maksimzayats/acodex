from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar, cast

from typing_extensions import Unpack

from acodex._internal.exec import build_exec_args
from acodex._internal.output_schema_file import UNSET, create_output_schema_file
from acodex._internal.thread_core import (
    build_turn_or_raise,
    initial_turn_state,
    parse_thread_event_jsonl,
    reduce_turn_state,
)
from acodex.exceptions import CodexThreadStreamNotConsumedError
from acodex.exec import AsyncCodexExec, CodexExec
from acodex.types.codex_options import CodexOptions
from acodex.types.events import ThreadEvent, ThreadStartedEvent
from acodex.types.input import Input
from acodex.types.thread_options import ThreadOptions
from acodex.types.turn import (
    AsyncRunStreamedResult,
    RunResult,
    RunStreamedResult,
)
from acodex.types.turn_options import TurnOptions

if TYPE_CHECKING:
    T = TypeVar("T", default=Any)
else:
    T = TypeVar("T")


_missing = object()


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
        output_type: type[T] = _missing,
        **turn_options: Unpack[TurnOptions],
    ) -> RunStreamedResult:
        """Provide input to the agent and stream turn events as they are produced.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.

        Returns:
            A streamed turn result with an iterator of parsed events.

        """
        state = initial_turn_state()
        stream_completed = False

        def build_result() -> RunResult:
            if not stream_completed:
                raise CodexThreadStreamNotConsumedError(
                    "streamed.result is unavailable until streamed.events is fully consumed",
                )
            return build_turn_or_raise(state)

        def event_generator() -> Iterator[ThreadEvent]:
            nonlocal state, stream_completed
            schema_file = create_output_schema_file(turn_options.get("output_schema", UNSET))
            line_stream: Iterator[str] | None = None
            try:
                exec_args = build_exec_args(
                    input=input,
                    options=self._options,
                    thread_options=self._thread_options,
                    thread_id=self._id,
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

                    state = reduce_turn_state(state, event)
                    yield event
                stream_completed = True
            finally:
                if line_stream is not None:
                    _close_if_possible(line_stream)
                schema_file.cleanup()

        return RunStreamedResult(events=event_generator(), result_factory=build_result)

    def run(
        self,
        input: Input,  # noqa: A002
        output_type: type[T] = _missing,
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.

        Returns:
            The completed turn with reduced items, final response, and usage.

        """
        streamed = self.run_streamed(input, **turn_options)
        events = streamed.events
        try:
            for _event in events:
                pass
        finally:
            _close_if_possible(events)

        return streamed.result


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
        output_type: type[T] = _missing,
        **turn_options: Unpack[TurnOptions],
    ) -> AsyncRunStreamedResult:
        """Provide input to the agent and stream turn events as they are produced.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.

        Returns:
            A streamed turn result with an async iterator of parsed events.

        """
        state = initial_turn_state()
        stream_completed = False

        def build_result() -> RunResult:
            if not stream_completed:
                raise CodexThreadStreamNotConsumedError(
                    "streamed.result is unavailable until streamed.events is fully consumed",
                )
            return build_turn_or_raise(state)

        async def event_generator() -> AsyncIterator[ThreadEvent]:
            nonlocal state, stream_completed
            schema_file = create_output_schema_file(turn_options.get("output_schema", UNSET))
            line_stream: AsyncIterator[str] | None = None
            try:
                exec_args = build_exec_args(
                    input=input,
                    options=self._options,
                    thread_options=self._thread_options,
                    thread_id=self._id,
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

                    state = reduce_turn_state(state, event)
                    yield event
                stream_completed = True
            finally:
                if line_stream is not None:
                    await _aclose_if_possible(line_stream)
                schema_file.cleanup()

        return AsyncRunStreamedResult(events=event_generator(), result_factory=build_result)

    async def run(
        self,
        input: Input,  # noqa: A002
        output_type: type[T] = _missing,
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.

        Returns:
            The completed turn with reduced items, final response, and usage.

        """
        streamed = await self.run_streamed(input, **turn_options)
        events = streamed.events
        try:
            async for _event in events:
                pass
        finally:
            await _aclose_if_possible(events)

        return streamed.result


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
