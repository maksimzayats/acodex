from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from acodex.types.items import ThreadItem


@dataclass(frozen=True, slots=True)
class ThreadStartedEvent:
    """Emitted when a new thread is started as the first event."""

    thread_id: str
    """Identifier of the new thread. This can be used to resume the thread later."""

    type: Literal["thread.started"] = field(default="thread.started", init=False)
    """Discriminator with value ``"thread.started"``."""


@dataclass(frozen=True, slots=True)
class TurnStartedEvent:
    """Emitted when a turn is started by sending a new prompt to the model.

    A turn encompasses all events that happen while the agent is processing the prompt.
    """

    type: Literal["turn.started"] = field(default="turn.started", init=False)
    """Discriminator with value ``"turn.started"``."""


@dataclass(frozen=True, slots=True)
class Usage:
    """Describes token usage for a completed turn."""

    input_tokens: int
    """Number of input tokens used during the turn."""

    cached_input_tokens: int
    """Number of cached input tokens used during the turn."""

    output_tokens: int
    """Number of output tokens used during the turn."""


@dataclass(frozen=True, slots=True)
class TurnCompletedEvent:
    """Emitted when a turn is completed.

    This is typically emitted right after the assistant response.

    """

    usage: Usage
    """Token usage for the completed turn."""

    type: Literal["turn.completed"] = field(default="turn.completed", init=False)
    """Discriminator with value ``"turn.completed"``."""


@dataclass(frozen=True, slots=True)
class ThreadError:
    """Fatal error payload for a failed turn."""

    message: str
    """Error message describing the failure."""


@dataclass(frozen=True, slots=True)
class TurnFailedEvent:
    """Indicates that a turn failed with an error."""

    error: ThreadError
    """Fatal error payload for the failed turn."""

    type: Literal["turn.failed"] = field(default="turn.failed", init=False)
    """Discriminator with value ``"turn.failed"``."""


@dataclass(frozen=True, slots=True)
class ItemStartedEvent:
    """Emitted when a new item is added to the thread.

    Typically, the item is initially in progress.

    """

    item: ThreadItem
    """Thread item payload that was started."""

    type: Literal["item.started"] = field(default="item.started", init=False)
    """Discriminator with value ``"item.started"``."""


@dataclass(frozen=True, slots=True)
class ItemUpdatedEvent:
    """Emitted when an item is updated."""

    item: ThreadItem
    """Updated thread item payload."""

    type: Literal["item.updated"] = field(default="item.updated", init=False)
    """Discriminator with value ``"item.updated"``."""


@dataclass(frozen=True, slots=True)
class ItemCompletedEvent:
    """Signals that an item has reached a terminal state.

    The terminal state may be success or failure depending on the item payload.

    """

    item: ThreadItem
    """Thread item payload in a terminal state."""

    type: Literal["item.completed"] = field(default="item.completed", init=False)
    """Discriminator with value ``"item.completed"``."""


@dataclass(frozen=True, slots=True)
class ThreadErrorEvent:
    """Represents an unrecoverable error emitted directly by the event stream."""

    message: str
    """Error message emitted by the stream."""

    type: Literal["error"] = field(default="error", init=False)
    """Discriminator with value ``"error"``."""


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
