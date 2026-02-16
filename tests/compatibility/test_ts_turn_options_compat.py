from __future__ import annotations

import asyncio
import threading
from typing import get_args, get_origin, get_type_hints

from typing_extensions import NotRequired

from acodex.types import turn_options as py_turn_options
from tests.compatibility._assertions import (
    assert_ts_expr_compatible,
    camel_to_snake,
    unwrap_not_required,
)
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_type_alias_parser import extract_exported_type_alias_rhs
from tools.compatibility.ts_type_expr import TsObject, parse_ts_type_expr


def test_turn_options_keys_optionality_and_types_match_typescript() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "turnOptions.ts").read_text(encoding="utf-8")
    ts_rhs = extract_exported_type_alias_rhs(ts_source, "TurnOptions")
    ts_expr = parse_ts_type_expr(ts_rhs)
    assert isinstance(ts_expr, TsObject), "TurnOptions must be an object type in TypeScript"

    ts_props = {camel_to_snake(prop.name): prop for prop in ts_expr.properties}
    py_keys = set(py_turn_options.TurnOptions.__annotations__)
    assert set(ts_props) == py_keys, (
        f"TurnOptions keys mismatch: TS={sorted(ts_props)}, Python={sorted(py_keys)}"
    )

    assert all(prop.optional for prop in ts_props.values()), (
        "All TurnOptions keys must be optional in TS"
    )

    py_hints = get_type_hints(
        py_turn_options.TurnOptions,
        include_extras=True,
        localns={"NotRequired": NotRequired, **py_turn_options.__dict__},
    )
    for key, ts_prop in ts_props.items():
        assert get_origin(py_hints[key]).__name__ == "NotRequired"
        py_hint = unwrap_not_required(py_hints[key])
        assert_ts_expr_compatible(ts_prop.type_expr, py_hint, resolver=_resolver)


def test_turn_signal_divergence_is_asserted() -> None:
    members = set(get_args(py_turn_options.TurnSignal))
    assert members == {threading.Event, asyncio.Event}, (
        "TurnSignal must be threading.Event | asyncio.Event per differences.md"
    )

    py_hints = get_type_hints(
        py_turn_options.TurnOptions,
        include_extras=True,
        localns={"NotRequired": NotRequired, **py_turn_options.__dict__},
    )
    assert unwrap_not_required(py_hints["signal"]) == py_turn_options.TurnSignal


def _resolver(name: str) -> object | None:
    return getattr(py_turn_options, name, None)
