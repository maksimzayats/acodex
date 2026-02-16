from __future__ import annotations

import importlib
import json
from typing import TYPE_CHECKING, Generic, TypeVar, cast

import jsonref

from acodex.exceptions import CodexStructuredResponseError
from acodex.types.turn_options import OutputSchemaInput

if TYPE_CHECKING:
    from pydantic import TypeAdapter

T = TypeVar("T")


def _build_type_adapter(output_type: type[T]) -> TypeAdapter[T]:
    try:
        pydantic_module = importlib.import_module("pydantic")
    except ModuleNotFoundError as error:
        if error.name == "pydantic":
            raise CodexStructuredResponseError(
                "Structured output with `output_type` requires Pydantic. "
                'Install it with: pip install "acodex[structured-output]".',
            ) from error
        raise

    type_adapter = pydantic_module.TypeAdapter
    return cast("TypeAdapter[T]", type_adapter(type=output_type))


class OutputTypeAdapter(Generic[T]):
    def __init__(
        self,
        output_type: type[T] | None = None,
        output_schema: OutputSchemaInput | None = None,
    ) -> None:
        self._output_schema = output_schema

        self._adapter: TypeAdapter[T] | None
        if output_type is not None:
            self._adapter = _build_type_adapter(output_type)
        else:
            self._adapter = None

    def json_schema(self) -> OutputSchemaInput | None:
        if self._output_schema is not None:
            return self._output_schema

        if self._adapter is None:
            return None

        schema = self._adapter.json_schema()
        self._ensure_additional_properties_is_false(schema)

        return jsonref.replace_refs(schema, base_uri="", proxies=False)

    def validate_json(self, json_string: str | bytes | bytearray) -> T:
        if self._adapter is not None:
            try:
                return self._adapter.validate_json(json_string)
            except Exception as error:
                raise CodexStructuredResponseError(
                    "Failed to validate structured response against output schema.",
                ) from error

        if self._output_schema is not None:
            try:
                return cast("T", json.loads(json_string))
            except Exception as error:
                raise CodexStructuredResponseError(
                    "Failed to parse structured response as JSON.",
                ) from error

        raise CodexStructuredResponseError(
            "No output schema available for validating structured response. "
            "Provide an `output_type` or `output_schema` to enable validation.",
        )

    def _ensure_additional_properties_is_false(self, schema: OutputSchemaInput) -> None:
        """Recursively set `additionalProperties` to `False` in the provided JSON schema and all nested subschemas."""
        if schema.get("type") == "object":
            schema["additionalProperties"] = False

        for value in schema.values():
            if isinstance(value, dict):
                self._ensure_additional_properties_is_false(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._ensure_additional_properties_is_false(item)
