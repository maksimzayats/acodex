from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, NoReturn, TypeAlias, TypedDict, TypeVar, cast

from acodex._output_schema_file import OutputSchemaFileHandle, create_output_schema_file
from acodex._parsing import parse_thread_event
from acodex.codex_options import CodexOptions
from acodex.events import (
    ItemCompletedEvent,
    ThreadEvent,
    ThreadStartedEvent,
    TurnCompletedEvent,
    TurnFailedEvent,
    Usage,
)
from acodex.exec import AsyncCodexExec, CodexExec, CodexExecArgs, _signal_is_set
from acodex.items import ThreadItem
from acodex.thread_options import ThreadOptions
from acodex.turn_options import TurnOptions, TurnSignal

if TYPE_CHECKING:
    from typing_extensions import Unpack


class UserInputText(TypedDict):
    """A text input to send to the agent."""

    type: Literal["text"]
    text: str


class UserInputLocalImage(TypedDict):
    """A local image input to send to the agent."""

    type: Literal["local_image"]
    path: str


UserInput: TypeAlias = UserInputText | UserInputLocalImage
Input: TypeAlias = str | list[UserInput]


@dataclass(frozen=True, slots=True)
class Turn:
    """Completed turn.

    This is the result returned by `run()`.
    """

    items: list[ThreadItem]
    final_response: str
    usage: Usage | None


EventsT = TypeVar("EventsT")


@dataclass(frozen=True, slots=True)
class StreamedTurn(Generic[EventsT]):
    """The result of the `run_streamed` method."""

    events: EventsT


class Thread:
    """Represent a thread of conversation with the agent.

    One thread can have multiple consecutive turns.
    """

    def __init__(
        self,
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
        """
        return StreamedTurn(
            events=self._run_streamed_internal(input=input, turn_options=turn_options),
        )

    def _run_streamed_internal(
        self,
        *,
        input: Input,  # noqa: A002
        turn_options: TurnOptions,
    ) -> Iterator[ThreadEvent]:
        setup = _prepare_stream_setup(
            input=input,
            turn_options=turn_options,
            options=self._options,
            thread_options=self._thread_options,
            thread_id=self._id,
        )
        exec_iter = self._exec.run(setup.exec_args)

        try:
            for line in exec_iter:
                event = _parse_jsonl_line(line)
                self._id = _update_thread_id_from_event(self._id, event)
                yield event
        finally:
            _close_if_possible(exec_iter)
            setup.schema_handle.cleanup()

    def run(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.
        """
        streamed = self.run_streamed(input, **turn_options)
        events_iter = streamed.events
        accumulator = _TurnAccumulator(
            items=[], final_response="", usage=None, failure_message=None
        )

        try:
            for event in events_iter:
                if accumulator.on_event(event):
                    break
        finally:
            if accumulator.failure_message is not None:
                _close_if_possible(events_iter)

        if accumulator.failure_message is not None:
            raise RuntimeError(accumulator.failure_message)

        return Turn(
            items=accumulator.items,
            final_response=accumulator.final_response,
            usage=accumulator.usage,
        )


class AsyncThread:
    """Represent a thread of conversation with the agent.

    One thread can have multiple consecutive turns.
    """

    def __init__(
        self,
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
        """
        return StreamedTurn(
            events=self._run_streamed_internal(input=input, turn_options=turn_options),
        )

    async def _run_streamed_internal(
        self,
        *,
        input: Input,  # noqa: A002
        turn_options: TurnOptions,
    ) -> AsyncIterator[ThreadEvent]:
        setup = _prepare_stream_setup(
            input=input,
            turn_options=turn_options,
            options=self._options,
            thread_options=self._thread_options,
            thread_id=self._id,
        )
        exec_iter = self._exec.run(setup.exec_args)

        try:
            async for line in exec_iter:
                event = _parse_jsonl_line(line)
                self._id = _update_thread_id_from_event(self._id, event)
                yield event
        finally:
            await _aclose_if_possible(exec_iter)
            await setup.schema_handle.acleanup()

    async def run(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.
        """
        streamed = await self.run_streamed(input, **turn_options)
        events_iter = streamed.events
        accumulator = _TurnAccumulator(
            items=[], final_response="", usage=None, failure_message=None
        )

        try:
            async for event in events_iter:
                if accumulator.on_event(event):
                    break
        finally:
            if accumulator.failure_message is not None:
                await _aclose_if_possible(events_iter)

        if accumulator.failure_message is not None:
            raise RuntimeError(accumulator.failure_message)

        return Turn(
            items=accumulator.items,
            final_response=accumulator.final_response,
            usage=accumulator.usage,
        )


RunResult: TypeAlias = Turn
RunStreamedResult: TypeAlias = StreamedTurn[Iterator[ThreadEvent]]
AsyncRunStreamedResult: TypeAlias = StreamedTurn[AsyncIterator[ThreadEvent]]


TURN_CANCELLED_MESSAGE = "Turn cancelled"


@dataclass(slots=True)
class _TurnAccumulator:
    items: list[ThreadItem]
    final_response: str
    usage: Usage | None
    failure_message: str | None

    def on_event(self, event: ThreadEvent) -> bool:
        if isinstance(event, ItemCompletedEvent):
            if event.item.type == "agent_message":
                self.final_response = event.item.text
            self.items.append(event.item)
        elif isinstance(event, TurnCompletedEvent):
            self.usage = event.usage
        elif isinstance(event, TurnFailedEvent):
            self.failure_message = event.error.message
            return True
        return False


@dataclass(frozen=True, slots=True)
class _PreparedStreamSetup:
    exec_args: CodexExecArgs
    schema_handle: OutputSchemaFileHandle


@dataclass(frozen=True, slots=True)
class _ExecContext:
    options: CodexOptions
    thread_options: ThreadOptions
    thread_id: str | None


def _build_exec_args(
    *,
    context: _ExecContext,
    prompt: str,
    images: list[str],
    schema_path: str | None,
    turn_signal: TurnSignal | None,
) -> CodexExecArgs:
    args_dict: dict[str, object] = {
        "input": prompt,
        "thread_id": context.thread_id,
        "images": images,
    }

    args_dict.update(
        {
            key: value
            for key, value in (
                ("base_url", context.options.get("base_url")),
                ("api_key", context.options.get("api_key")),
                ("model", context.thread_options.get("model")),
                ("sandbox_mode", context.thread_options.get("sandbox_mode")),
                ("working_directory", context.thread_options.get("working_directory")),
                ("additional_directories", context.thread_options.get("additional_directories")),
                ("skip_git_repo_check", context.thread_options.get("skip_git_repo_check")),
                ("model_reasoning_effort", context.thread_options.get("model_reasoning_effort")),
                ("network_access_enabled", context.thread_options.get("network_access_enabled")),
                ("web_search_mode", context.thread_options.get("web_search_mode")),
                ("web_search_enabled", context.thread_options.get("web_search_enabled")),
                ("approval_policy", context.thread_options.get("approval_policy")),
            )
            if value is not None
        },
    )

    if schema_path is not None:
        args_dict["output_schema_file"] = schema_path

    if turn_signal is not None:
        args_dict["signal"] = turn_signal

    return cast("CodexExecArgs", args_dict)


def _prepare_stream_setup(
    *,
    input: Input,  # noqa: A002
    turn_options: TurnOptions,
    options: CodexOptions,
    thread_options: ThreadOptions,
    thread_id: str | None,
) -> _PreparedStreamSetup:
    prompt, images = _normalize_input(input)
    turn_signal = turn_options.get("signal")
    _ensure_not_cancelled(turn_signal)

    schema_handle = create_output_schema_file(turn_options.get("output_schema"))
    context = _ExecContext(options=options, thread_options=thread_options, thread_id=thread_id)
    exec_args = _build_exec_args(
        context=context,
        prompt=prompt,
        images=images,
        schema_path=schema_handle.schema_path,
        turn_signal=turn_signal,
    )
    return _PreparedStreamSetup(exec_args=exec_args, schema_handle=schema_handle)


def _ensure_not_cancelled(turn_signal: TurnSignal | None) -> None:
    if turn_signal is not None and _signal_is_set(turn_signal):
        raise RuntimeError(TURN_CANCELLED_MESSAGE)


def _parse_jsonl_line(line: str) -> ThreadEvent:
    parsed_raw: object
    try:
        parsed_raw = json.loads(line)
    except json.JSONDecodeError as error:
        message = f"Failed to parse item: {line}"
        raise ValueError(message) from error
    return parse_thread_event(parsed_raw)


def _update_thread_id_from_event(current_id: str | None, event: ThreadEvent) -> str | None:
    if isinstance(event, ThreadStartedEvent):
        return event.thread_id
    return current_id


def _close_if_possible(iterator: object) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


async def _aclose_if_possible(iterator: object) -> None:
    aclose = getattr(iterator, "aclose", None)
    if callable(aclose):
        await aclose()


def _normalize_input(input: Input) -> tuple[str, list[str]]:  # noqa: A002
    if isinstance(input, str):
        return input, []
    if not isinstance(input, list):
        _raise_type_error("input must be a string or a list of user input blocks")

    prompt_parts: list[str] = []
    images: list[str] = []
    for index, item in enumerate(input):
        if not isinstance(item, dict):
            _raise_type_error(f"input[{index}] must be an object")
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text")
            if not isinstance(text, str):
                _raise_type_error(f"input[{index}].text must be a string")
            prompt_parts.append(text)
        elif item_type == "local_image":
            path = item.get("path")
            if not isinstance(path, str):
                _raise_type_error(f"input[{index}].path must be a string")
            images.append(path)
        else:
            _raise_value_error(f"Unknown input block type: {item_type!r}")

    return "\n\n".join(prompt_parts), images


def _raise_type_error(message: str) -> NoReturn:
    raise TypeError(message)


def _raise_value_error(message: str, error: Exception | None = None) -> NoReturn:
    if error is None:
        raise ValueError(message)
    raise ValueError(message) from error
