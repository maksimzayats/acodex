from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from typing import cast

import pytest
from typing_extensions import TypedDict

import acodex._internal.output_type as output_type_module
from acodex._internal.output_type import OutputTypeAdapter
from acodex.exceptions import CodexStructuredResponseError
from acodex.types.turn_options import OutputSchemaInput


class _TypedPayload(TypedDict):
    name: str
    count: int


class _TypedComment(TypedDict):
    id: int
    severity: int
    comment: str


class _TypedCheckResult(TypedDict):
    comments: list[_TypedComment]


class _TypedNullableCommentResult(TypedDict):
    comment: _TypedComment | None


skip_output_type_tests_on_py315 = pytest.mark.skipif(
    sys.version_info >= (3, 15),
    reason="Pydantic is not available on Python 3.15+.",
)


def _iter_schema_nodes(value: object) -> Iterator[OutputSchemaInput]:
    if isinstance(value, dict):
        node = cast("OutputSchemaInput", value)
        yield node
        for child in node.values():
            yield from _iter_schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_schema_nodes(child)


@skip_output_type_tests_on_py315
def test_json_schema_prefers_explicit_output_schema_over_output_type() -> None:
    schema: OutputSchemaInput = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    adapter: OutputTypeAdapter[_TypedPayload] = OutputTypeAdapter(
        output_type=_TypedPayload,
        output_schema=schema,
    )

    assert adapter.json_schema() == schema


@skip_output_type_tests_on_py315
def test_json_schema_from_output_type_sets_additional_properties_false() -> None:
    adapter: OutputTypeAdapter[_TypedPayload] = OutputTypeAdapter(output_type=_TypedPayload)

    schema = adapter.json_schema()
    assert schema is not None
    assert schema["additionalProperties"] is False


@skip_output_type_tests_on_py315
def test_json_schema_from_nested_output_type_is_json_serializable() -> None:
    adapter: OutputTypeAdapter[_TypedCheckResult] = OutputTypeAdapter(
        output_type=_TypedCheckResult,
    )
    schema = adapter.json_schema()
    assert schema is not None
    assert isinstance(json.dumps(schema), str)


def test_json_schema_without_output_type_or_output_schema_returns_none() -> None:
    adapter: OutputTypeAdapter[str] = OutputTypeAdapter()

    assert adapter.json_schema() is None


@skip_output_type_tests_on_py315
def test_json_schema_from_nested_output_type_sets_additional_properties_false_recursively() -> None:
    adapter: OutputTypeAdapter[_TypedCheckResult] = OutputTypeAdapter(
        output_type=_TypedCheckResult,
    )

    schema = adapter.json_schema()
    assert schema is not None

    for node in _iter_schema_nodes(schema):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False


@skip_output_type_tests_on_py315
def test_json_schema_from_nested_output_type_replaces_refs() -> None:
    adapter: OutputTypeAdapter[_TypedCheckResult] = OutputTypeAdapter(
        output_type=_TypedCheckResult,
    )

    schema = adapter.json_schema()
    assert schema is not None

    for node in _iter_schema_nodes(schema):
        assert "$ref" not in node


@skip_output_type_tests_on_py315
def test_json_schema_does_not_inject_additional_properties_for_non_object_nodes() -> None:
    adapter: OutputTypeAdapter[_TypedCheckResult] = OutputTypeAdapter(
        output_type=_TypedCheckResult,
    )

    schema = adapter.json_schema()
    assert schema is not None

    for node in _iter_schema_nodes(schema):
        if node.get("type") != "object":
            assert "additionalProperties" not in node


@skip_output_type_tests_on_py315
def test_json_schema_from_union_output_type_sets_additional_properties_false_for_objects() -> None:
    adapter: OutputTypeAdapter[_TypedNullableCommentResult] = OutputTypeAdapter(
        output_type=_TypedNullableCommentResult,
    )

    schema = adapter.json_schema()
    assert schema is not None

    for node in _iter_schema_nodes(schema):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False


@skip_output_type_tests_on_py315
def test_validate_json_with_output_type_returns_validated_payload() -> None:
    adapter: OutputTypeAdapter[_TypedPayload] = OutputTypeAdapter(output_type=_TypedPayload)

    payload = adapter.validate_json('{"name":"ok","count":1}')

    assert payload == {"name": "ok", "count": 1}


@skip_output_type_tests_on_py315
def test_validate_json_with_output_type_invalid_payload_raises_structured_error() -> None:
    adapter: OutputTypeAdapter[_TypedPayload] = OutputTypeAdapter(output_type=_TypedPayload)

    with pytest.raises(
        CodexStructuredResponseError,
        match="Failed to validate structured response against output schema\\.",
    ) as error:
        adapter.validate_json('{"name":"ok","count":"bad"}')

    assert error.value.__cause__ is not None


def test_validate_json_with_output_schema_only_parses_json_payload() -> None:
    schema: OutputSchemaInput = {"type": "object"}
    adapter: OutputTypeAdapter[dict[str, object]] = OutputTypeAdapter(output_schema=schema)

    payload = adapter.validate_json('{"ok":true,"count":2}')

    assert payload == {"ok": True, "count": 2}


def test_validate_json_with_output_schema_only_invalid_json_raises_structured_error() -> None:
    schema: OutputSchemaInput = {"type": "object"}
    adapter: OutputTypeAdapter[dict[str, object]] = OutputTypeAdapter(output_schema=schema)

    with pytest.raises(
        CodexStructuredResponseError,
        match="Failed to parse structured response as JSON\\.",
    ) as error:
        adapter.validate_json("not-json")

    assert error.value.__cause__ is not None


def test_validate_json_without_output_type_or_schema_raises_structured_error_without_pydantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def _import_module(name: str, package: str | None = None) -> object:
        if name == "pydantic":
            raise AssertionError("pydantic should not be imported")
        return real_import_module(name, package)

    monkeypatch.setattr(output_type_module.importlib, "import_module", _import_module)

    adapter: OutputTypeAdapter[str] = OutputTypeAdapter()

    with pytest.raises(
        CodexStructuredResponseError,
        match=(
            "No output schema available for validating structured response\\. "
            "Provide an `output_type` or `output_schema` to enable validation\\."
        ),
    ):
        adapter.validate_json("plain text response")


def test_validate_json_with_output_schema_only_works_without_pydantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def _import_module(name: str, package: str | None = None) -> object:
        if name == "pydantic":
            raise AssertionError("pydantic should not be imported")
        return real_import_module(name, package)

    monkeypatch.setattr(output_type_module.importlib, "import_module", _import_module)

    schema: OutputSchemaInput = {"type": "object"}
    adapter: OutputTypeAdapter[dict[str, object]] = OutputTypeAdapter(output_schema=schema)

    payload = adapter.validate_json('{"ok":true}')

    assert payload == {"ok": True}


def test_output_type_missing_pydantic_raises_structured_error_with_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def _import_module(name: str, package: str | None = None) -> object:
        if name == "pydantic":
            raise ModuleNotFoundError("No module named 'pydantic'", name="pydantic")
        return real_import_module(name, package)

    monkeypatch.setattr(output_type_module.importlib, "import_module", _import_module)

    with pytest.raises(
        CodexStructuredResponseError,
        match='pip install "acodex\\[structured-output\\]"',
    ) as error:
        OutputTypeAdapter(output_type=_TypedPayload)

    cause = error.value.__cause__
    assert isinstance(cause, ModuleNotFoundError)
    assert cause.name == "pydantic"


def test_output_type_re_raises_non_pydantic_module_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def _import_module(name: str, package: str | None = None) -> object:
        if name == "pydantic":
            raise ModuleNotFoundError("No module named 'pydantic_core'", name="pydantic_core")
        return real_import_module(name, package)

    monkeypatch.setattr(output_type_module.importlib, "import_module", _import_module)

    with pytest.raises(ModuleNotFoundError) as error:
        OutputTypeAdapter(output_type=_TypedPayload)

    assert error.value.name == "pydantic_core"
