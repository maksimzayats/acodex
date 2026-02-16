from __future__ import annotations

import json
from typing import Generic, TypeVar, cast

from pydantic import TypeAdapter

from acodex.exceptions import CodexStructuredResponseError
from acodex.types.turn_options import OutputSchemaInput

T = TypeVar("T")


class OutputTypeAdapter(Generic[T]):
    def __init__(
        self,
        output_type: type[T] | None = None,
        output_schema: OutputSchemaInput | None = None,
    ) -> None:
        self._output_schema = output_schema

        self._adapter: TypeAdapter[T] | None
        if output_type is not None:
            self._adapter = TypeAdapter(type=output_type)
        else:
            self._adapter = None

    def json_schema(self) -> OutputSchemaInput | None:
        if self._output_schema is not None:
            return self._output_schema

        if self._adapter is None:
            return None

        schema = self._adapter.json_schema()
        schema.setdefault("additionalProperties", False)

        return schema

    def validate_json(self, json_string: str | bytes | bytearray) -> T:
        if self._adapter is None:
            return cast("T", json.loads(json_string))

        try:
            return self._adapter.validate_json(json_string)
        except Exception as e:
            raise CodexStructuredResponseError(
                "Failed to validate structured response against output schema.",
            ) from e
