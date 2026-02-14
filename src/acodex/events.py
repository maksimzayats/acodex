from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

from acodex.items import ThreadItem


class ThreadStartedEvent(TypedDict):
    """Emitted when a new thread is started as the first event."""

    type: Literal["thread.started"]
    thread_id: str


class TurnStartedEvent(TypedDict):
    """Emitted when a turn is started by sending a new prompt to the model."""

    type: Literal["turn.started"]


class Usage(TypedDict):
    """Describes the usage of tokens during a turn."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class TurnCompletedEvent(TypedDict):
    """Emitted when a turn is completed."""

    type: Literal["turn.completed"]
    usage: Usage


class ThreadError(TypedDict):
    """Fatal error emitted by the stream."""

    message: str


class TurnFailedEvent(TypedDict):
    """Indicates that a turn failed with an error."""

    type: Literal["turn.failed"]
    error: ThreadError


class ItemStartedEvent(TypedDict):
    """Emitted when a new item is added to the thread."""

    type: Literal["item.started"]
    item: ThreadItem


class ItemUpdatedEvent(TypedDict):
    """Emitted when an item is updated."""

    type: Literal["item.updated"]
    item: ThreadItem


class ItemCompletedEvent(TypedDict):
    """Signals that an item has reached a terminal state."""

    type: Literal["item.completed"]
    item: ThreadItem


class ThreadErrorEvent(TypedDict):
    """Represents an unrecoverable error emitted directly by the event stream."""

    type: Literal["error"]
    message: str


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
