from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Generic, TypeAlias, TypeVar

from acodex.types.events import ThreadEvent, Usage
from acodex.types.items import ThreadItem

EventsT = TypeVar("EventsT")


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
