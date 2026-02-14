from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired

JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | JsonObject


class TurnOptions(TypedDict):
    output_schema: NotRequired[JsonObject]
    signal: NotRequired[object]
