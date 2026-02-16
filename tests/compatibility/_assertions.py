from __future__ import annotations

import dataclasses
import functools
import operator
import types
from collections.abc import Callable
from typing import Literal, Union, get_args, get_origin, get_type_hints

from typing_extensions import assert_never

from tools.compatibility.ts_type_expr import (
    TsArray,
    TsGeneric,
    TsIdentifier,
    TsIndexSignature,
    TsObject,
    TsObjectProperty,
    TsPrimitive,
    TsStringLiteral,
    TsTypeExpr,
    TsUnion,
)


def camel_to_snake(name: str) -> str:
    result: list[str] = []
    for index, char in enumerate(name):
        if not char.isupper():
            result.append(char)
            continue

        previous = name[index - 1] if index else ""
        next_char = name[index + 1] if index + 1 < len(name) else ""
        if index and (previous.islower() or (next_char and next_char.islower())):
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def unwrap_not_required(hint: object) -> object:
    origin = get_origin(hint)
    if origin is None:
        return hint

    origin_name = getattr(origin, "__name__", None)
    if origin_name == "NotRequired":
        args = get_args(hint)
        if len(args) != 1:
            msg = f"Expected NotRequired[T], got: {hint!r}"
            raise AssertionError(msg)
        return args[0]

    return hint


def dataclass_field_required(field_info: dataclasses.Field[object]) -> bool:
    return (
        field_info.default is dataclasses.MISSING
        and field_info.default_factory is dataclasses.MISSING
    )


def assert_ts_expr_compatible(
    ts: TsTypeExpr,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    """Assert a vendored TS type expression is compatible with a Python type hint."""
    _assert_ts_expr_compatible(ts, py, resolver=resolver)


def _assert_ts_expr_compatible(
    ts: TsTypeExpr,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    if isinstance(ts, TsUnion):
        _assert_ts_union_compatible(ts, py, resolver=resolver)
        return

    if isinstance(ts, TsIdentifier):
        resolved = resolver(ts.name)
        if resolved is None:
            return
        _assert_python_expected_compatible(resolved, py, resolver=resolver)
        return

    py_members = _python_union_members(py)
    if py_members is not None:
        _assert_ts_non_union_python_union_compatible(
            ts,
            py,
            py_members=py_members,
            resolver=resolver,
        )
        return

    _assert_ts_non_union_non_union_compatible(ts, py, resolver=resolver)


def _assert_ts_non_union_python_union_compatible(
    ts: TsTypeExpr,
    py: object,
    *,
    py_members: tuple[object, ...],
    resolver: Callable[[str], object | None],
) -> None:
    if isinstance(ts, TsPrimitive) and ts.name == "unknown":
        return
    if isinstance(ts, TsIdentifier) and resolver(ts.name) is None:
        return
    if isinstance(ts, TsPrimitive) and ts.name == "number":
        for member in py_members:
            _assert_ts_expr_compatible(ts, member, resolver=resolver)
        return

    msg = f"Unexpected Python union for non-union TS type: TS={ts!r} Python={py!r}"
    raise AssertionError(msg)


def _assert_ts_non_union_non_union_compatible(
    ts: TsTypeExpr,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    if isinstance(ts, TsPrimitive):
        _assert_ts_primitive_compatible(ts, py)
    elif isinstance(ts, TsStringLiteral):
        _assert_ts_string_literal_compatible(ts, py)
    elif isinstance(ts, TsArray):
        _assert_ts_array_compatible(ts, py, resolver=resolver)
    elif isinstance(ts, TsGeneric):
        _assert_ts_generic_compatible(ts, py, resolver=resolver)
    elif isinstance(ts, TsObject):
        _assert_ts_object_compatible(ts, py, resolver=resolver)
    else:
        msg = f"Unhandled TS type expression: {ts!r}"
        raise TypeError(msg)


def _assert_ts_union_compatible(
    ts: TsUnion,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    py_members = _python_union_members(py)
    if py_members is None:
        msg = f"Expected Python union for TS union, got: {py!r}"
        raise AssertionError(msg)

    for ts_member in ts.members:
        if not any(
            _ts_member_matches_python(ts_member, member, resolver=resolver) for member in py_members
        ):
            msg = f"Missing TS union member in Python union: TS={ts_member!r} Python={py!r}"
            raise AssertionError(msg)

    for py_member in py_members:
        if not any(
            _ts_member_matches_python(ts_member, py_member, resolver=resolver)
            for ts_member in ts.members
        ):
            msg = (
                f"Extra Python union member not covered by TS union: TS={ts!r} Python={py_member!r}"
            )
            raise AssertionError(msg)


def _ts_member_matches_python(
    ts: TsTypeExpr,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> bool:
    try:
        _assert_ts_expr_compatible(ts, py, resolver=resolver)
    except AssertionError:
        return False
    return True


def _assert_ts_primitive_compatible(ts: TsPrimitive, py: object) -> None:
    if ts.name == "unknown":
        return

    if ts.name == "null":
        assert py in {None, types.NoneType, type(None)}, f"Expected None for TS null, got: {py!r}"
        return

    if ts.name == "string":
        if _is_python_literal_string(py):
            return
        assert py is str, f"Expected str for TS string, got: {py!r}"
        return

    if ts.name == "boolean":
        assert py is bool, f"Expected bool for TS boolean, got: {py!r}"
        return

    if ts.name == "number":
        assert py in {int, float}, f"Expected int/float for TS number, got: {py!r}"
        return

    assert_never(ts.name)


def _assert_ts_string_literal_compatible(ts: TsStringLiteral, py: object) -> None:
    origin = get_origin(py)
    if origin is Literal:
        args = get_args(py)
        assert args == (ts.value,), f"Literal mismatch: TS={ts.value!r} Python={args!r}"
        return
    msg = f"Expected typing.Literal[{ts.value!r}] for TS string literal, got: {py!r}"
    raise AssertionError(msg)


def _assert_ts_array_compatible(
    ts: TsArray,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    origin = get_origin(py)
    if origin is not list:
        msg = f"Expected list[T] for TS array, got: {py!r}"
        raise AssertionError(msg)

    args = get_args(py)
    if len(args) != 1:
        msg = f"Expected list[T] with one argument, got: {py!r}"
        raise AssertionError(msg)

    _assert_ts_expr_compatible(ts.element, args[0], resolver=resolver)


def _assert_ts_generic_compatible(
    ts: TsGeneric,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    if ts.name == "Record":
        origin = get_origin(py)
        if origin is not dict:
            msg = f"Expected dict[K, V] for TS Record, got: {py!r}"
            raise AssertionError(msg)
        args = get_args(py)
        if len(args) != 2:
            msg = f"Expected dict[K, V] with two args, got: {py!r}"
            raise AssertionError(msg)
        if len(ts.args) != 2:
            msg = f"Expected Record<K, V>, got: {ts!r}"
            raise AssertionError(msg)
        _assert_ts_expr_compatible(ts.args[0], args[0], resolver=resolver)
        _assert_ts_expr_compatible(ts.args[1], args[1], resolver=resolver)
        return

    resolved = resolver(ts.name)
    if resolved is None:
        return
    _assert_python_expected_compatible(resolved, py, resolver=resolver)


def _assert_ts_object_compatible(
    ts: TsObject,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    if ts.index_signature is not None and not ts.properties:
        _assert_index_signature_compatible(ts.index_signature, py, resolver=resolver)
        return

    if isinstance(py, type) and dataclasses.is_dataclass(py):
        _assert_object_dataclass_compatible(ts, py, resolver=resolver)
        return

    msg = f"Unsupported TS object compatibility target: TS={ts!r} Python={py!r}"
    raise AssertionError(msg)


def _assert_index_signature_compatible(
    ts: TsIndexSignature,
    py: object,
    *,
    resolver: Callable[[str], object | None],
) -> None:
    origin = get_origin(py)
    if origin is not dict:
        msg = f"Expected dict[K, V] for TS index signature, got: {py!r}"
        raise AssertionError(msg)
    args = get_args(py)
    if len(args) != 2:
        msg = f"Expected dict[K, V] for TS index signature, got: {py!r}"
        raise AssertionError(msg)
    _assert_ts_expr_compatible(ts.key_type, args[0], resolver=resolver)
    _assert_ts_expr_compatible(ts.value_type, args[1], resolver=resolver)


def _assert_object_dataclass_compatible(
    ts: TsObject,
    py: type[object],
    *,
    resolver: Callable[[str], object | None],
) -> None:
    ts_properties: dict[str, TsObjectProperty] = {prop.name: prop for prop in ts.properties}
    py_fields = {field_info.name: field_info for field_info in dataclasses.fields(py)}  # type: ignore[arg-type]
    assert set(ts_properties) == set(py_fields), (
        f"Object fields mismatch: TS={sorted(ts_properties)}, Python={sorted(py_fields)}"
    )

    type_hints = get_type_hints(py, include_extras=True)
    for name, ts_prop in ts_properties.items():
        field_info = py_fields[name]
        if name != "type":
            if ts_prop.optional:
                assert not dataclass_field_required(field_info), (
                    f"{py.__name__}.{name} is optional in TS but required in Python"
                )
            else:
                assert dataclass_field_required(field_info), (
                    f"{py.__name__}.{name} is required in TS but optional in Python"
                )

        py_hint = type_hints[name]
        if ts_prop.optional:
            py_hint = _strip_optional_none(py_hint)
        _assert_ts_expr_compatible(ts_prop.type_expr, py_hint, resolver=resolver)


def _assert_python_expected_compatible(
    expected: object,
    actual: object,
    *,
    resolver: Callable[[str], object | None],
    seen: set[tuple[str, str]] | None = None,
) -> None:
    if seen is None:
        seen = set()

    expected = _resolve_python_forward_annotation(expected, resolver=resolver)
    actual = _resolve_python_forward_annotation(actual, resolver=resolver)

    seen_key = (repr(expected), repr(actual))
    if seen_key in seen:
        return
    next_seen = set(seen)
    next_seen.add(seen_key)

    if expected is object:
        return

    if expected == actual:
        return

    expected_origin = get_origin(expected)
    actual_origin = get_origin(actual)

    if _is_python_union(expected):
        _assert_python_union_expected_compatible(
            expected,
            actual,
            resolver=resolver,
            seen=next_seen,
        )
        return

    if expected_origin is list and actual_origin is list:
        _assert_python_list_expected_compatible(
            expected,
            actual,
            resolver=resolver,
            seen=next_seen,
        )
        return

    if expected_origin is dict and actual_origin is dict:
        _assert_python_dict_expected_compatible(
            expected,
            actual,
            resolver=resolver,
            seen=next_seen,
        )
        return

    msg = f"Type mismatch: expected={expected!r} actual={actual!r}"
    raise AssertionError(msg)


def _is_python_union(annotation: object) -> bool:
    return _python_union_members(annotation) is not None


def _python_union_members(annotation: object) -> tuple[object, ...] | None:
    args = get_args(annotation)
    if not args:
        return None
    origin = get_origin(annotation)
    if origin in {Union, types.UnionType}:
        return args
    return None


def _strip_optional_none(annotation: object) -> object:
    members = _python_union_members(annotation)
    if members is None:
        return annotation
    non_none_members = tuple(member for member in members if member is not type(None))
    if len(non_none_members) == 1:
        return non_none_members[0]
    if len(non_none_members) == len(members):
        return annotation
    return functools.reduce(operator.or_, non_none_members)


def _is_python_literal_string(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is not Literal:
        return False
    args = get_args(annotation)
    return len(args) == 1 and isinstance(args[0], str)


def _python_expected_member_matches_actual(
    expected_member: object,
    actual_member: object,
    *,
    resolver: Callable[[str], object | None],
    seen: set[tuple[str, str]],
) -> bool:
    try:
        _assert_python_expected_compatible(
            expected_member,
            actual_member,
            resolver=resolver,
            seen=seen,
        )
    except AssertionError:
        return False
    return True


def _resolve_python_forward_annotation(
    annotation: object,
    *,
    resolver: Callable[[str], object | None],
) -> object:
    if isinstance(annotation, str):
        resolved = resolver(annotation)
        if resolved is not None:
            return resolved
        return annotation

    forward_arg = getattr(annotation, "__forward_arg__", None)
    if isinstance(forward_arg, str):
        resolved = resolver(forward_arg)
        if resolved is not None:
            return resolved

    return annotation


def _assert_python_union_expected_compatible(
    expected: object,
    actual: object,
    *,
    resolver: Callable[[str], object | None],
    seen: set[tuple[str, str]],
) -> None:
    expected_members = _python_union_members(expected)
    actual_members = _python_union_members(actual)
    if expected_members is None or actual_members is None:
        msg = f"Expected Python union for both types, got: {expected!r} and {actual!r}"
        raise AssertionError(msg)

    for expected_member in expected_members:
        if any(
            _python_expected_member_matches_actual(
                expected_member,
                actual_member,
                resolver=resolver,
                seen=seen,
            )
            for actual_member in actual_members
        ):
            continue
        msg = f"Union mismatch: expected={expected!r} actual={actual!r}"
        raise AssertionError(msg)

    for actual_member in actual_members:
        if any(
            _python_expected_member_matches_actual(
                expected_member,
                actual_member,
                resolver=resolver,
                seen=seen,
            )
            for expected_member in expected_members
        ):
            continue
        msg = f"Union mismatch: expected={expected!r} actual={actual!r}"
        raise AssertionError(msg)


def _assert_python_list_expected_compatible(
    expected: object,
    actual: object,
    *,
    resolver: Callable[[str], object | None],
    seen: set[tuple[str, str]],
) -> None:
    expected_args = get_args(expected)
    actual_args = get_args(actual)
    if len(expected_args) != 1 or len(actual_args) != 1:
        msg = f"Unsupported list args: expected={expected!r} actual={actual!r}"
        raise AssertionError(msg)

    _assert_python_expected_compatible(
        expected_args[0],
        actual_args[0],
        resolver=resolver,
        seen=seen,
    )


def _assert_python_dict_expected_compatible(
    expected: object,
    actual: object,
    *,
    resolver: Callable[[str], object | None],
    seen: set[tuple[str, str]],
) -> None:
    expected_args = get_args(expected)
    actual_args = get_args(actual)
    if len(expected_args) != 2 or len(actual_args) != 2:
        msg = f"Unsupported dict args: expected={expected!r} actual={actual!r}"
        raise AssertionError(msg)

    _assert_python_expected_compatible(
        expected_args[0],
        actual_args[0],
        resolver=resolver,
        seen=seen,
    )
    _assert_python_expected_compatible(
        expected_args[1],
        actual_args[1],
        resolver=resolver,
        seen=seen,
    )
