from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from typing_extensions import NotRequired

from acodex.types import thread_options as py_thread_options
from tests.compatibility._assertions import (
    assert_ts_expr_compatible,
    camel_to_snake,
    unwrap_not_required,
)
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_type_alias_parser import extract_exported_type_alias_rhs
from tools.compatibility.ts_type_expr import TsObject, TsStringLiteral, TsUnion, parse_ts_type_expr


def test_thread_option_literal_unions_match_typescript() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "threadOptions.ts").read_text(encoding="utf-8")
    literal_aliases = (
        "ApprovalMode",
        "SandboxMode",
        "ModelReasoningEffort",
        "WebSearchMode",
    )
    for alias_name in literal_aliases:
        ts_rhs = extract_exported_type_alias_rhs(ts_source, alias_name)
        ts_expr = parse_ts_type_expr(ts_rhs)
        assert isinstance(ts_expr, TsUnion), f"{alias_name} must be a union in TypeScript"
        ts_literals = {
            member.value for member in ts_expr.members if isinstance(member, TsStringLiteral)
        }
        assert len(ts_literals) == len(ts_expr.members), (
            f"{alias_name} must be a string-literal union in TS"
        )

        py_literals = set(get_args(getattr(py_thread_options, alias_name)))
        assert ts_literals == py_literals, (
            f"{alias_name} literal union mismatch: TS={sorted(ts_literals)} Python={sorted(py_literals)}"
        )


def test_thread_options_keys_optionality_and_types_match_typescript() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "threadOptions.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "ThreadOptions")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsObject), "ThreadOptions must be an object type in TypeScript"

    ts_props = {camel_to_snake(prop.name): prop for prop in ts_expr.properties}
    py_keys = set(py_thread_options.ThreadOptions.__annotations__)
    assert set(ts_props) == py_keys, (
        f"ThreadOptions keys mismatch: TS={sorted(ts_props)}, Python={sorted(py_keys)}"
    )

    assert all(prop.optional for prop in ts_props.values()), (
        "All ThreadOptions keys must be optional in TS"
    )

    py_hints = get_type_hints(
        py_thread_options.ThreadOptions,
        include_extras=True,
        localns={"NotRequired": NotRequired, **py_thread_options.__dict__},
    )
    for key, ts_prop in ts_props.items():
        assert get_origin(py_hints[key]).__name__ == "NotRequired"
        py_hint = unwrap_not_required(py_hints[key])
        assert_ts_expr_compatible(ts_prop.type_expr, py_hint, resolver=_resolver)


def _resolver(name: str) -> object | None:
    return getattr(py_thread_options, name, None)
