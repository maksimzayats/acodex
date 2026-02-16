from __future__ import annotations

import types
from dataclasses import MISSING, Field, fields, is_dataclass
from typing import Literal, Union, get_args, get_origin, get_type_hints

from acodex.types import events as py_events, items as py_items
from tests.compatibility._assertions import assert_ts_expr_compatible
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_type_alias_parser import TsAlias, parse_exported_type_aliases
from tools.compatibility.ts_type_expr import parse_ts_type_expr


def test_events_aliases_exist_in_python_sdk() -> None:
    ts_aliases = _load_event_aliases()
    missing_aliases = sorted(
        alias_name for alias_name in ts_aliases if not hasattr(py_events, alias_name)
    )

    assert not missing_aliases, "Missing event aliases from Python SDK: " + ", ".join(
        missing_aliases,
    )


def test_events_object_aliases_match_dataclass_shapes() -> None:
    ts_aliases = _load_event_aliases()

    for alias_name, ts_alias in ts_aliases.items():
        if ts_alias.kind != "object":
            continue

        py_symbol = getattr(py_events, alias_name)
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


def test_events_cross_type_references_match_python_types() -> None:
    turn_completed_hints = get_type_hints(py_events.TurnCompletedEvent, include_extras=True)
    turn_failed_hints = get_type_hints(py_events.TurnFailedEvent, include_extras=True)

    assert turn_completed_hints["usage"] is py_events.Usage, (
        "TurnCompletedEvent.usage must resolve to acodex.types.events.Usage"
    )
    assert turn_failed_hints["error"] is py_events.ThreadError, (
        "TurnFailedEvent.error must resolve to acodex.types.events.ThreadError"
    )

    for item_event_type in (
        py_events.ItemStartedEvent,
        py_events.ItemUpdatedEvent,
        py_events.ItemCompletedEvent,
    ):
        item_hints = get_type_hints(item_event_type, include_extras=True)
        assert item_hints["item"] == py_items.ThreadItem, (
            f"{item_event_type.__name__}.item must resolve to acodex.types.items.ThreadItem"
        )


def test_thread_event_union_membership_matches_typescript() -> None:
    ts_alias = _load_event_aliases()["ThreadEvent"]
    assert ts_alias.kind == "identifier_union", (
        "ThreadEvent in TypeScript must be an identifier union"
    )
    ts_members = set(ts_alias.union_members or ())
    py_members = {member.__name__ for member in get_args(py_events.ThreadEvent)}

    assert ts_members == py_members, (
        f"ThreadEvent union mismatch: TS={sorted(ts_members)}, Python={sorted(py_members)}"
    )


def _load_event_aliases() -> dict[str, TsAlias]:
    events_ts_path = VENDOR_TS_SDK_SRC / "events.ts"
    return parse_exported_type_aliases(events_ts_path.read_text(encoding="utf-8"))


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
    if hasattr(py_events, name):
        return getattr(py_events, name)
    if hasattr(py_items, name):
        return getattr(py_items, name)
    return None


def _parse_string_literal(type_expr: str) -> str | None:
    stripped_type_expr = type_expr.strip()
    if len(stripped_type_expr) < 2:
        return None

    quote = stripped_type_expr[0]
    if quote not in {'"', "'"} or stripped_type_expr[-1] != quote:
        return None

    return stripped_type_expr[1:-1]
