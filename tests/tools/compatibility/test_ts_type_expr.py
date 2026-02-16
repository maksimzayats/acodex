from __future__ import annotations

import pytest

from tools.compatibility.ts_type_expr import (
    TsArray,
    TsGeneric,
    TsIdentifier,
    TsIndexSignature,
    TsObject,
    TsObjectProperty,
    TsPrimitive,
    TsStringLiteral,
    TsUnion,
    parse_ts_type_expr,
)


def test_parse_primitives_and_identifier() -> None:
    assert parse_ts_type_expr("string") == TsPrimitive(name="string")
    assert parse_ts_type_expr("number") == TsPrimitive(name="number")
    assert parse_ts_type_expr("boolean") == TsPrimitive(name="boolean")
    assert parse_ts_type_expr("unknown") == TsPrimitive(name="unknown")
    assert parse_ts_type_expr("null") == TsPrimitive(name="null")
    assert parse_ts_type_expr("Foo") == TsIdentifier(name="Foo")


def test_parse_string_literals_including_escaped_quotes_and_backslashes() -> None:
    assert parse_ts_type_expr("'x'") == TsStringLiteral(value="x")
    assert parse_ts_type_expr('"x"') == TsStringLiteral(value="x")
    assert parse_ts_type_expr('"a\\\\b\\"c"') == TsStringLiteral(value='a\\b"c')
    assert parse_ts_type_expr("'a\\\\b\\'c'") == TsStringLiteral(value="a\\b'c")


def test_parse_unions_are_flattened_and_leading_pipe_is_tolerated() -> None:
    assert parse_ts_type_expr("string | number | boolean") == TsUnion(
        members=(
            TsPrimitive(name="string"),
            TsPrimitive(name="number"),
            TsPrimitive(name="boolean"),
        ),
    )
    assert parse_ts_type_expr("| string | number") == TsUnion(
        members=(TsPrimitive(name="string"), TsPrimitive(name="number")),
    )


def test_parse_parenthesized_union_array_and_postfix_array_chaining() -> None:
    assert parse_ts_type_expr("(string | number)[]") == TsArray(
        element=TsUnion(members=(TsPrimitive(name="string"), TsPrimitive(name="number"))),
    )
    assert parse_ts_type_expr("Foo[][]") == TsArray(
        element=TsArray(element=TsIdentifier(name="Foo")),
    )


def test_parse_generics_and_nested_generics() -> None:
    assert parse_ts_type_expr("Promise<string>") == TsGeneric(
        name="Promise",
        args=(TsPrimitive(name="string"),),
    )
    assert parse_ts_type_expr("Record<string, number>") == TsGeneric(
        name="Record",
        args=(TsPrimitive(name="string"), TsPrimitive(name="number")),
    )
    assert parse_ts_type_expr("Foo<Bar<Baz>>") == TsGeneric(
        name="Foo",
        args=(TsGeneric(name="Bar", args=(TsIdentifier(name="Baz"),)),),
    )


def test_parse_objects_with_optional_properties_and_mixed_separators() -> None:
    parsed = parse_ts_type_expr("{ foo: string; bar?: number, baz: Foo,,; }")
    assert parsed == TsObject(
        properties=(
            TsObjectProperty(name="foo", optional=False, type_expr=TsPrimitive(name="string")),
            TsObjectProperty(name="bar", optional=True, type_expr=TsPrimitive(name="number")),
            TsObjectProperty(name="baz", optional=False, type_expr=TsIdentifier(name="Foo")),
        ),
        index_signature=None,
    )


def test_parse_objects_with_index_signatures() -> None:
    assert parse_ts_type_expr("{ [key: string]: number }") == TsObject(
        properties=(),
        index_signature=TsIndexSignature(
            key_name="key",
            key_type=TsPrimitive(name="string"),
            value_type=TsPrimitive(name="number"),
        ),
    )
    assert parse_ts_type_expr("{ a: string; [k: string]: number }") == TsObject(
        properties=(
            TsObjectProperty(name="a", optional=False, type_expr=TsPrimitive(name="string")),
        ),
        index_signature=TsIndexSignature(
            key_name="k",
            key_type=TsPrimitive(name="string"),
            value_type=TsPrimitive(name="number"),
        ),
    )


@pytest.mark.parametrize(
    ("expr", "message_substring"),
    [
        ('"unterminated', "Unterminated string literal"),
        ("string number", "Unexpected token"),
        ("{ foo: string", "Unterminated object type"),
        ("{ [a: string]: number; [b: string]: number }", "multiple index signatures"),
        ("{ 'foo': string }", "Expected property name"),
        ("{ ['k': string]: number }", "Expected index signature name"),
    ],
)
def test_parse_ts_type_expr_error_paths(expr: str, message_substring: str) -> None:
    with pytest.raises(ValueError, match=message_substring):
        parse_ts_type_expr(expr)
