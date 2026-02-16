from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired


JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonValue: TypeAlias = str | int | float | bool | list["JsonValue"] | JsonObject | None
TurnSignal: TypeAlias = threading.Event | asyncio.Event
OutputSchemaInput: TypeAlias = JsonObject


class TurnOptions(TypedDict):
    """Options for a single turn.

    Set the event (`event.set()`) to request cancellation.
    Use `threading.Event` for synchronous flows and `asyncio.Event` for asynchronous flows.
    """

    output_schema: NotRequired[OutputSchemaInput]
    signal: NotRequired[TurnSignal]
