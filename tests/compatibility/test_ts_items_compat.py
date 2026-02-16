from __future__ import annotations

import types
from dataclasses import MISSING, Field, fields, is_dataclass
from typing import Literal, Union, get_args, get_origin, get_type_hints

from acodex.types import items as py_items
from tests.compatibility._assertions import assert_ts_expr_compatible
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_type_alias_parser import (
    TsAlias,
    TsProperty,
    parse_exported_type_aliases,
)
from tools.compatibility.ts_type_expr import parse_ts_type_expr


def test_items_aliases_exist_in_python_sdk() -> None:
    ts_aliases = _load_item_aliases()
    missing_aliases = sorted(
        alias_name for alias_name in ts_aliases if not hasattr(py_items, alias_name)
    )

    assert not missing_aliases, "Missing item aliases from Python SDK: " + ", ".join(
        missing_aliases,
    )


def test_item_string_literal_unions_match_typescript() -> None:
    ts_aliases = _load_item_aliases()
    literal_union_aliases = (
        "CommandExecutionStatus",
        "PatchChangeKind",
        "PatchApplyStatus",
        "McpToolCallStatus",
    )

    for alias_name in literal_union_aliases:
        ts_alias = ts_aliases[alias_name]
        assert ts_alias.kind == "string_union", (
            f"{alias_name} in TypeScript must be a string-literal union"
        )
        ts_literals = set(ts_alias.string_literals or ())
        py_literals = set(get_args(getattr(py_items, alias_name)))
        assert ts_literals == py_literals, (
            f"{alias_name} literal union mismatch: TS={sorted(ts_literals)}, "
            f"Python={sorted(py_literals)}"
        )


def test_item_object_aliases_match_dataclass_shapes() -> None:
    ts_aliases = _load_item_aliases()

    for alias_name, ts_alias in ts_aliases.items():
        if ts_alias.kind != "object":
            continue

        py_symbol = getattr(py_items, alias_name)
        assert is_dataclass(py_symbol), f"{alias_name} must be a dataclass in Python SDK"

        ts_properties = ts_alias.properties
        assert ts_properties is not None, f"{alias_name} object alias must expose parsed properties"

        py_fields = {field_info.name: field_info for field_info in fields(py_symbol)}
        assert set(ts_properties) == set(py_fields), (
            f"{alias_name} fields mismatch: TS={sorted(ts_properties)}, Python={sorted(py_fields)}"
        )

        type_hints = get_type_hints(py_symbol, include_extras=True)
        for property_name, ts_property in ts_properties.items():
            py_field = py_fields[property_name]

            if property_name == "type":
                expected_discriminator = _parse_string_literal(ts_property.type_expr)
                assert expected_discriminator is not None, (
                    f"{alias_name}.type must be a string literal in TypeScript"
                )
                assert py_field.default == expected_discriminator, (
                    f"{alias_name}.type default mismatch: "
                    f"TS={expected_discriminator!r}, Python={py_field.default!r}"
                )
                python_type_hint = type_hints["type"]
                assert get_origin(python_type_hint) is Literal, (
                    f"{alias_name}.type must be annotated as typing.Literal in Python SDK"
                )
                assert get_args(python_type_hint) == (expected_discriminator,), (
                    f"{alias_name}.type literal annotation mismatch: "
                    f"TS={expected_discriminator!r}, Python={get_args(python_type_hint)!r}"
                )
                continue

            if ts_property.optional:
                assert not _is_required_dataclass_field(py_field), (
                    f"{alias_name}.{property_name} is optional in TS but required in Python"
                )
            else:
                assert _is_required_dataclass_field(py_field), (
                    f"{alias_name}.{property_name} is required in TS but optional in Python"
                )

            ts_expr = parse_ts_type_expr(ts_property.type_expr)
            py_hint: object = type_hints[property_name]
            if ts_property.optional:
                py_hint = _strip_optional_none(py_hint)
            assert_ts_expr_compatible(ts_expr, py_hint, resolver=_resolver)


def test_optional_item_fields_match_typescript() -> None:
    ts_aliases = _load_item_aliases()
    optional_expectations: tuple[tuple[str, str], ...] = (
        ("CommandExecutionItem", "exit_code"),
        ("McpToolCallItem", "result"),
        ("McpToolCallItem", "error"),
    )

    for alias_name, property_name in optional_expectations:
        ts_property = _require_property(
            ts_aliases,
            alias_name=alias_name,
            property_name=property_name,
        )
        assert ts_property.optional, f"{alias_name}.{property_name} must be optional in TypeScript"

        py_field_map = {
            field_info.name: field_info for field_info in fields(getattr(py_items, alias_name))
        }
        assert not _is_required_dataclass_field(py_field_map[property_name]), (
            f"{alias_name}.{property_name} must be optional in Python"
        )


def test_mcp_tool_call_inline_object_shapes_match_python_helpers() -> None:
    ts_aliases = _load_item_aliases()
    ts_mcp_tool_call_alias = ts_aliases["McpToolCallItem"]
    ts_properties = ts_mcp_tool_call_alias.properties
    assert ts_properties is not None, "McpToolCallItem must expose parsed properties"

    ts_result_property = _require_property(
        ts_aliases,
        alias_name="McpToolCallItem",
        property_name="result",
    )
    ts_error_property = _require_property(
        ts_aliases,
        alias_name="McpToolCallItem",
        property_name="error",
    )

    assert ts_result_property.inline_object is not None, (
        "McpToolCallItem.result must be parsed as an inline TypeScript object"
    )
    assert ts_error_property.inline_object is not None, (
        "McpToolCallItem.error must be parsed as an inline TypeScript object"
    )

    python_hints = get_type_hints(py_items.McpToolCallItem, include_extras=True)
    python_result_type = _get_optional_union_member(python_hints["result"])
    python_error_type = _get_optional_union_member(python_hints["error"])

    assert python_result_type is py_items.McpToolCallResult, (
        "McpToolCallItem.result must resolve to acodex.types.items.McpToolCallResult | None"
    )
    assert python_error_type is py_items.McpToolCallError, (
        "McpToolCallItem.error must resolve to acodex.types.items.McpToolCallError | None"
    )

    ts_result_fields = set((ts_result_property.inline_object.properties or {}).keys())
    ts_error_fields = set((ts_error_property.inline_object.properties or {}).keys())
    py_result_fields = {field_info.name for field_info in fields(py_items.McpToolCallResult)}
    py_error_fields = {field_info.name for field_info in fields(py_items.McpToolCallError)}

    assert ts_result_fields == py_result_fields, (
        "McpToolCallResult field mismatch: "
        f"TS={sorted(ts_result_fields)}, Python={sorted(py_result_fields)}"
    )
    assert ts_error_fields == py_error_fields, (
        "McpToolCallError field mismatch: "
        f"TS={sorted(ts_error_fields)}, Python={sorted(py_error_fields)}"
    )


def test_thread_item_union_membership_matches_typescript() -> None:
    ts_alias = _load_item_aliases()["ThreadItem"]
    assert ts_alias.kind == "identifier_union", (
        "ThreadItem in TypeScript must be an identifier union"
    )
    ts_members = set(ts_alias.union_members or ())
    py_members = {member.__name__ for member in get_args(py_items.ThreadItem)}

    assert ts_members == py_members, (
        f"ThreadItem union mismatch: TS={sorted(ts_members)}, Python={sorted(py_members)}"
    )


def _load_item_aliases() -> dict[str, TsAlias]:
    items_ts_path = VENDOR_TS_SDK_SRC / "items.ts"
    return parse_exported_type_aliases(items_ts_path.read_text(encoding="utf-8"))


def _is_required_dataclass_field(field_info: Field[object]) -> bool:
    return field_info.default is MISSING and field_info.default_factory is MISSING


def _strip_optional_none(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin not in {Union, types.UnionType}:
        return annotation
    args = get_args(annotation)
    non_none = tuple(arg for arg in args if arg is not type(None))
    if len(non_none) == 1:
        return non_none[0]
    return annotation


def _resolver(name: str) -> object | None:
    return getattr(py_items, name, None)


def _parse_string_literal(type_expr: str) -> str | None:
    stripped_type_expr = type_expr.strip()
    if len(stripped_type_expr) < 2:
        return None

    quote = stripped_type_expr[0]
    if quote not in {'"', "'"} or stripped_type_expr[-1] != quote:
        return None

    return stripped_type_expr[1:-1]


def _require_property(
    aliases: dict[str, TsAlias],
    *,
    alias_name: str,
    property_name: str,
) -> TsProperty:
    ts_alias = aliases[alias_name]
    ts_properties = ts_alias.properties
    assert ts_properties is not None, f"{alias_name} must expose parsed object properties"
    assert property_name in ts_properties, (
        f"{alias_name} missing expected property: {property_name}"
    )
    return ts_properties[property_name]


def _get_optional_union_member(annotation: object) -> type[object]:
    non_none_members = [member for member in get_args(annotation) if member is not type(None)]
    assert len(non_none_members) == 1, (
        f"Expected an optional union with one concrete member, got: {annotation!r}"
    )

    union_member = non_none_members[0]
    assert isinstance(union_member, type), f"Expected type member, got: {union_member!r}"
    return union_member
