from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import Generic, TypeAlias, TypeVar

from acodex.types.events import ThreadEvent, Usage
from acodex.types.items import ThreadItem

EventsT = TypeVar("EventsT")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Turn(Generic[T]):
    """Completed turn.

    This is the result returned by `run()`.
    """

    items: list[ThreadItem]
    final_response: str
    usage: Usage | None
    structured_response_factory: Callable[[], T] = field(repr=False, compare=False)

    @property
    def structured_response(self) -> T:
        """Return the structured response."""
        return self.structured_response_factory()


@dataclass(frozen=True, slots=True)
class StreamedTurn(Generic[EventsT]):
    """The result of the `run_streamed` method."""

    events: EventsT


RunResult: TypeAlias = Turn[T]


@dataclass(frozen=True, slots=True)
class RunStreamedResult(StreamedTurn[Iterator[ThreadEvent]], Generic[T]):
    """The synchronous result of `run_streamed`."""

    result_factory: Callable[[], RunResult[T]] = field(repr=False, compare=False)

    @property
    def result(self) -> RunResult[T]:
        """Return the reduced turn after full stream exhaustion."""
        return self.result_factory()


@dataclass(frozen=True, slots=True)
class AsyncRunStreamedResult(StreamedTurn[AsyncIterator[ThreadEvent]], Generic[T]):
    """The asynchronous result of `run_streamed`."""

    result_factory: Callable[[], RunResult[T]] = field(repr=False, compare=False)

    @property
    def result(self) -> RunResult[T]:
        """Return the reduced turn after full stream exhaustion."""
        return self.result_factory()
