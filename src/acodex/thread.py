from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypeAlias, TypedDict, TypeVar

from acodex.codex_options import CodexOptions
from acodex.events import ThreadEvent, Usage
from acodex.exec import AsyncCodexExec, CodexExec
from acodex.items import ThreadItem
from acodex.thread_options import ThreadOptions
from acodex.turn_options import TurnOptions

if TYPE_CHECKING:
    from typing_extensions import Unpack

EventsT = TypeVar("EventsT")


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


@dataclass(frozen=True, slots=True)
class StreamedTurn(Generic[EventsT]):
    """The result of the `run_streamed` method."""

    events: EventsT


RunResult: TypeAlias = Turn
RunStreamedResult: TypeAlias = StreamedTurn[Iterator[ThreadEvent]]
AsyncRunStreamedResult: TypeAlias = StreamedTurn[AsyncIterator[ThreadEvent]]


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
        _ = (input, turn_options)
        raise NotImplementedError

    def run(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `threading.Event` in synchronous flows.
        """
        _ = (input, turn_options)
        raise NotImplementedError


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
        _ = (input, turn_options)
        raise NotImplementedError

    async def run(
        self,
        input: Input,  # noqa: A002
        **turn_options: Unpack[TurnOptions],
    ) -> RunResult:
        """Provide input to the agent and return the completed turn.

        Set `turn_options["signal"]` via `event.set()` to request cancellation.
        Use `asyncio.Event` in asynchronous flows.
        """
        _ = (input, turn_options)
        raise NotImplementedError
