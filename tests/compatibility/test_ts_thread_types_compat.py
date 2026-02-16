from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import get_args, get_type_hints

from acodex.types import events as py_events, input as py_input, items as py_items, turn as py_turn
from tests.compatibility._assertions import assert_ts_expr_compatible, camel_to_snake
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_type_alias_parser import extract_exported_type_alias_rhs
from tools.compatibility.ts_type_expr import TsObject, TsUnion, parse_ts_type_expr


def test_turn_alias_matches_python_dataclass() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "thread.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "Turn")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsObject), "Turn must be an object type in TypeScript"

    ts_props = {camel_to_snake(prop.name): prop for prop in ts_expr.properties}
    py_symbol = py_turn.Turn
    assert is_dataclass(py_symbol), "acodex.types.turn.Turn must be a dataclass"

    py_fields = {field_info.name: field_info for field_info in fields(py_symbol)}
    assert set(ts_props) <= set(py_fields), (
        f"Python Turn must include TS Turn fields: TS={sorted(ts_props)}, Python={sorted(py_fields)}"
    )

    python_only_fields = set(py_fields) - set(ts_props)
    assert python_only_fields == {"structured_response_factory"}, (
        f"Unexpected Python-only Turn fields: {sorted(python_only_fields)}"
    )
    assert isinstance(getattr(py_symbol, "structured_response", None), property), (
        "Python Turn must expose structured_response as a property"
    )

    py_hints = get_type_hints(py_symbol, include_extras=True)
    for name, ts_prop in ts_props.items():
        assert_ts_expr_compatible(ts_prop.type_expr, py_hints[name], resolver=_resolver)


def test_user_input_union_variants_match_python_dataclasses() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "thread.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "UserInput")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsUnion), "UserInput must be a union in TypeScript"

    py_union_members = set(get_args(py_input.UserInput))
    assert py_union_members == {py_input.UserInputText, py_input.UserInputLocalImage}, (
        "Python UserInput union must cover both variants"
    )

    for member in ts_expr.members:
        assert isinstance(member, TsObject), "UserInput union members must be object types in TS"
        assert_ts_expr_compatible(
            member,
            _select_python_user_input_variant(member),
            resolver=_resolver,
        )


def test_input_alias_matches_python_union() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "thread.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "Input")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert_ts_expr_compatible(ts_expr, py_input.Input, resolver=_resolver)


def _select_python_user_input_variant(ts_object: TsObject) -> type[object]:
    discriminator = next((prop for prop in ts_object.properties if prop.name == "type"), None)
    assert discriminator is not None, "UserInput variant must have a type discriminator"
    assert discriminator.optional is False, "UserInput.type must be required in TS"

    py_type_hint = get_type_hints(py_input.UserInputText, include_extras=True)["type"]
    if ts_object.properties and _matches_discriminator(ts_object, py_type_hint):
        return py_input.UserInputText

    py_type_hint = get_type_hints(py_input.UserInputLocalImage, include_extras=True)["type"]
    if ts_object.properties and _matches_discriminator(ts_object, py_type_hint):
        return py_input.UserInputLocalImage

    msg = f"Unsupported UserInput variant: {ts_object!r}"
    raise AssertionError(msg)


def _matches_discriminator(ts_object: TsObject, py_discriminator_hint: object) -> bool:
    for prop in ts_object.properties:
        if prop.name != "type":
            continue
        try:
            assert_ts_expr_compatible(prop.type_expr, py_discriminator_hint, resolver=_resolver)
        except AssertionError:
            return False
        return True
    return False


def _resolver(name: str) -> object | None:
    for module in (py_input, py_turn, py_items, py_events):
        if hasattr(module, name):
            return getattr(module, name)
    return None
