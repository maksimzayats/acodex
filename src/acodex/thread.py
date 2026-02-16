from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar, cast

from typing_extensions import Unpack

from acodex._internal.exec import build_exec_args
from acodex._internal.output_schema_file import create_output_schema_file
from acodex._internal.output_type import OutputTypeAdapter
from acodex._internal.thread_core import (
    build_turn_or_raise,
    initial_turn_state,
    parse_thread_event_jsonl,
    reduce_turn_state,
)
from acodex.exceptions import CodexThreadStreamNotConsumedError
from acodex.exec import AsyncCodexExec, CodexExec
from acodex.types.codex_options import CodexOptions
from acodex.types.events import (
    ThreadErrorEvent,
    ThreadEvent,
    ThreadStartedEvent,
    TurnFailedEvent,
)
from acodex.types.input import Input
from acodex.types.thread_options import ThreadOptions
from acodex.types.turn import AsyncRunStreamedResult, RunResult, RunStreamedResult
from acodex.types.turn_options import TurnOptions

if TYPE_CHECKING:
    T = TypeVar("T", default=Any)
else:
    T = TypeVar("T")


logger = logging.getLogger(__name__)


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
        logger.debug("Created Thread instance (thread_id=%s)", self._id)

    @property
    def id(self) -> str | None:
        """Return the ID of the thread.

        The ID is populated after the first turn starts.
        """
        return self._id

    def run_streamed(
        self,
        input: Input,  # noqa: A002
        output_type: type[T] | None = None,
        **turn_options: Unpack[TurnOptions],
    ) -> RunStreamedResult[T]:
        """Provide input to the agent and stream turn events as they are produced.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.

        Returns:
            A streamed turn result with an iterator of parsed events.

        """
        logger.info(
            "Starting streamed turn request (thread_id=%s, output_type=%s, output_schema=%s)",
            self._id,
            output_type is not None,
            turn_options.get("output_schema") is not None,
        )
        state = initial_turn_state()
        stream_completed = False

        output_type_adapter = OutputTypeAdapter(
            output_type=output_type,
            output_schema=turn_options.get("output_schema"),
        )

        def build_result() -> RunResult[T]:
            if not stream_completed:
                raise CodexThreadStreamNotConsumedError(
                    "streamed.result is unavailable until streamed.events is fully consumed",
                )
            return build_turn_or_raise(state, output_type_adapter=output_type_adapter)

        def event_generator() -> Iterator[ThreadEvent]:
            nonlocal state, stream_completed
            schema_file = create_output_schema_file(schema=output_type_adapter.json_schema())
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
                        logger.info("Assigned thread ID from event stream: %s", self._id)

                    log_method = (
                        logger.warning
                        if isinstance(event, (TurnFailedEvent, ThreadErrorEvent))
                        else logger.debug
                    )
                    log_method(
                        "Received event class=%s type=%s thread_id=%s event=%r",
                        event.__class__.__name__,
                        event.type,
                        self._id,
                        event,
                    )
                    state = reduce_turn_state(state, event)
                    yield event
                stream_completed = True
                logger.info("Completed streamed turn request (thread_id=%s)", self._id)
            finally:
                if line_stream is not None:
                    _close_if_possible(line_stream)
                schema_file.cleanup()
                logger.debug("Cleaned up streamed turn resources (thread_id=%s)", self._id)

        return RunStreamedResult(events=event_generator(), result_factory=build_result)

    def run(
        self,
        input: Input,  # noqa: A002
        output_type: type[T] | None = None,
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult[T]:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.

        Returns:
            The completed turn with reduced items, final response, and usage.

        """
        logger.info("Running turn request to completion (thread_id=%s)", self._id)
        streamed = self.run_streamed(input, output_type=output_type, **turn_options)
        events = streamed.events
        try:
            for _event in events:
                pass
        finally:
            _close_if_possible(events)

        logger.info("Completed turn request (thread_id=%s)", self._id)
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
        logger.debug("Created AsyncThread instance (thread_id=%s)", self._id)

    @property
    def id(self) -> str | None:
        """Return the ID of the thread.

        The ID is populated after the first turn starts.
        """
        return self._id

    async def run_streamed(
        self,
        input: Input,  # noqa: A002
        output_type: type[T] | None = None,
        **turn_options: Unpack[TurnOptions],
    ) -> AsyncRunStreamedResult[T]:
        """Provide input to the agent and stream turn events as they are produced.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.

        Returns:
            A streamed turn result with an async iterator of parsed events.

        """
        logger.info(
            "Starting async streamed turn request (thread_id=%s, output_type=%s, output_schema=%s)",
            self._id,
            output_type is not None,
            turn_options.get("output_schema") is not None,
        )
        state = initial_turn_state()
        stream_completed = False

        output_type_adapter = OutputTypeAdapter(
            output_type=output_type,
            output_schema=turn_options.get("output_schema"),
        )

        def build_result() -> RunResult[T]:
            if not stream_completed:
                raise CodexThreadStreamNotConsumedError(
                    "streamed.result is unavailable until streamed.events is fully consumed",
                )
            return build_turn_or_raise(state, output_type_adapter=output_type_adapter)

        async def event_generator() -> AsyncIterator[ThreadEvent]:
            nonlocal state, stream_completed
            schema_file = create_output_schema_file(schema=output_type_adapter.json_schema())
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
                        logger.info("Assigned async thread ID from event stream: %s", self._id)

                    log_method = (
                        logger.warning
                        if isinstance(event, (TurnFailedEvent, ThreadErrorEvent))
                        else logger.debug
                    )
                    log_method(
                        "Received event class=%s type=%s thread_id=%s event=%r",
                        event.__class__.__name__,
                        event.type,
                        self._id,
                        event,
                    )
                    state = reduce_turn_state(state, event)
                    yield event
                stream_completed = True
                logger.info("Completed async streamed turn request (thread_id=%s)", self._id)
            finally:
                if line_stream is not None:
                    await _aclose_if_possible(line_stream)
                schema_file.cleanup()
                logger.debug("Cleaned up async streamed turn resources (thread_id=%s)", self._id)

        return AsyncRunStreamedResult(events=event_generator(), result_factory=build_result)

    async def run(
        self,
        input: Input,  # noqa: A002
        output_type: type[T] | None = None,
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult[T]:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.

        Returns:
            The completed turn with reduced items, final response, and usage.

        """
        logger.info("Running async turn request to completion (thread_id=%s)", self._id)
        streamed = await self.run_streamed(input, output_type=output_type, **turn_options)
        events = streamed.events
        try:
            async for _event in events:
                pass
        finally:
            await _aclose_if_possible(events)

        logger.info("Completed async turn request (thread_id=%s)", self._id)
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
