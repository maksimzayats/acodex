from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import TypeAdapter

from acodex.types.turn_options import OutputSchemaInput

T = TypeVar("T")


class OutputTypeAdapter(Generic[T]):
    def __init__(self, output_type: type[T]) -> None:
        self._output_type = output_type
        self._adapter = TypeAdapter(type=output_type)

    def json_schema(self) -> OutputSchemaInput:
        schema = self._adapter.json_schema()
        schema.setdefault("additionalProperties", False)

        return schema

    def validate_json(self, json_string: str | bytes | bytearray) -> T:
        return self._adapter.validate_json(json_string)
