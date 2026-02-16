from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from typing_extensions import NotRequired

from acodex.types import codex_options as py_codex_options
from tests.compatibility._assertions import (
    assert_ts_expr_compatible,
    camel_to_snake,
    unwrap_not_required,
)
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_type_alias_parser import extract_exported_type_alias_rhs
from tools.compatibility.ts_type_expr import (
    TsArray,
    TsIdentifier,
    TsObject,
    TsPrimitive,
    TsUnion,
    parse_ts_type_expr,
)


def test_codex_options_keys_optionality_and_types_match_typescript() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "codexOptions.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "CodexOptions")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsObject), "CodexOptions must be an object type in TypeScript"

    ts_props = {camel_to_snake(prop.name): prop for prop in ts_expr.properties}
    py_keys = set(py_codex_options.CodexOptions.__annotations__)

    assert set(ts_props) == py_keys, (
        f"CodexOptions keys mismatch: TS={sorted(ts_props)}, Python={sorted(py_keys)}"
    )

    assert all(prop.optional for prop in ts_props.values()), (
        "All CodexOptions keys must be optional in TS"
    )

    py_hints = get_type_hints(
        py_codex_options.CodexOptions,
        include_extras=True,
        localns={"NotRequired": NotRequired, **py_codex_options.__dict__},
    )
    for key, ts_prop in ts_props.items():
        assert get_origin(py_hints[key]).__name__ == "NotRequired"
        py_hint = unwrap_not_required(py_hints[key])
        assert_ts_expr_compatible(ts_prop.type_expr, py_hint, resolver=_resolver)


def test_codex_config_value_union_contains_expected_members_and_excludes_null() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "codexOptions.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "CodexConfigValue")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsUnion), "CodexConfigValue must be a union in TypeScript"

    assert not any(
        isinstance(member, TsPrimitive) and member.name == "null" for member in ts_expr.members
    ), "CodexConfigValue must not include null in TypeScript"

    assert any(
        isinstance(member, TsPrimitive) and member.name == "string" for member in ts_expr.members
    )
    assert any(
        isinstance(member, TsPrimitive) and member.name == "number" for member in ts_expr.members
    )
    assert any(
        isinstance(member, TsPrimitive) and member.name == "boolean" for member in ts_expr.members
    )
    assert any(
        isinstance(member, TsArray)
        and isinstance(member.element, TsIdentifier)
        and member.element.name == "CodexConfigValue"
        for member in ts_expr.members
    ), "CodexConfigValue must include CodexConfigValue[] in TypeScript"
    assert any(
        isinstance(member, TsIdentifier) and member.name == "CodexConfigObject"
        for member in ts_expr.members
    ), "CodexConfigValue must include CodexConfigObject in TypeScript"

    py_union_members = get_args(py_codex_options.CodexConfigValue)
    assert type(None) not in py_union_members, "CodexConfigValue must not include None in Python"


def test_codex_config_object_index_signature_matches_python_shape() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "codexOptions.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "CodexConfigObject")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsObject), "CodexConfigObject must be an object type in TypeScript"
    assert ts_expr.index_signature is not None, (
        "CodexConfigObject must use an index signature in TypeScript"
    )
    assert ts_expr.properties == (), (
        "CodexConfigObject must not have named properties in TypeScript"
    )

    py_alias = py_codex_options.CodexConfigObject
    assert get_origin(py_alias) is dict, "CodexConfigObject must be dict[...] in Python"
    assert_ts_expr_compatible(ts_expr, py_alias, resolver=_resolver)


def _resolver(name: str) -> object | None:
    return getattr(py_codex_options, name, None)
