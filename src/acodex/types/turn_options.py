from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypedDict, TypeVar

if TYPE_CHECKING:
    from typing_extensions import NotRequired

    T = TypeVar("T", default=Any)
else:
    T = TypeVar("T")


JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | JsonObject | None
TurnSignal: TypeAlias = threading.Event | asyncio.Event
OutputSchemaInput: TypeAlias = JsonObject


class TurnOptions(TypedDict, Generic[T]):
    """Options for a single turn.

    Set the event (`event.set()`) to request cancellation.
    Use `threading.Event` for synchronous flows and `asyncio.Event` for asynchronous flows.
    """

    output_schema: NotRequired[OutputSchemaInput]
    output_type: NotRequired[type[T]]
    signal: NotRequired[TurnSignal]
