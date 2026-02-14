from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from acodex.items import ThreadItem


@dataclass(frozen=True, slots=True)
class ThreadStartedEvent:
    """Emitted when a new thread is started as the first event."""

    thread_id: str
    type: Literal["thread.started"] = field(default="thread.started", init=False)


@dataclass(frozen=True, slots=True)
class TurnStartedEvent:
    """Emitted when a turn is started by sending a new prompt to the model."""

    type: Literal["turn.started"] = field(default="turn.started", init=False)


@dataclass(frozen=True, slots=True)
class Usage:
    """Describes the usage of tokens during a turn."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class TurnCompletedEvent:
    """Emitted when a turn is completed."""

    usage: Usage
    type: Literal["turn.completed"] = field(default="turn.completed", init=False)


@dataclass(frozen=True, slots=True)
class ThreadError:
    """Fatal error emitted by the stream."""

    message: str


@dataclass(frozen=True, slots=True)
class TurnFailedEvent:
    """Indicates that a turn failed with an error."""

    error: ThreadError
    type: Literal["turn.failed"] = field(default="turn.failed", init=False)


@dataclass(frozen=True, slots=True)
class ItemStartedEvent:
    """Emitted when a new item is added to the thread."""

    item: ThreadItem
    type: Literal["item.started"] = field(default="item.started", init=False)


@dataclass(frozen=True, slots=True)
class ItemUpdatedEvent:
    """Emitted when an item is updated."""

    item: ThreadItem
    type: Literal["item.updated"] = field(default="item.updated", init=False)


@dataclass(frozen=True, slots=True)
class ItemCompletedEvent:
    """Signals that an item has reached a terminal state."""

    item: ThreadItem
    type: Literal["item.completed"] = field(default="item.completed", init=False)


@dataclass(frozen=True, slots=True)
class ThreadErrorEvent:
    """Represents an unrecoverable error emitted directly by the event stream."""

    message: str
    type: Literal["error"] = field(default="error", init=False)


ThreadEvent: TypeAlias = (
    ThreadStartedEvent
    | TurnStartedEvent
    | TurnCompletedEvent
    | TurnFailedEvent
    | ItemStartedEvent
    | ItemUpdatedEvent
    | ItemCompletedEvent
    | ThreadErrorEvent
)
