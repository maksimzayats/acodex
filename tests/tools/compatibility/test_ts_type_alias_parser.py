from __future__ import annotations

import pytest

from tools.compatibility import ts_type_alias_parser as parser
from tools.compatibility.ts_type_alias_parser import (
    TsAlias,
    TsProperty,
    extract_exported_type_alias_rhs,
    parse_exported_type_aliases,
)


def test_parse_exported_type_aliases_parses_multiple_declarations() -> None:
    ts_source = """
    export type Alpha = "a" | "b";
    export type Beta = Foo | Bar;
    """

    aliases = parse_exported_type_aliases(ts_source)

    assert aliases == {
        "Alpha": TsAlias(name="Alpha", kind="string_union", string_literals=("a", "b")),
        "Beta": TsAlias(name="Beta", kind="identifier_union", union_members=("Foo", "Bar")),
    }


def test_extract_exported_type_alias_rhs_returns_trimmed_rhs_for_named_alias() -> None:
    ts_source = """
    export type Other = "x";
    export type Target =   Foo | Bar   ;
    """

    assert extract_exported_type_alias_rhs(ts_source, "Target") == "Foo | Bar"


def test_strip_comments_removes_comments_and_preserves_strings_and_newlines() -> None:
    ts_source = """
    export type Demo = {
      value: "https://example.test//path"; // remove this
      marker: "/* keep me */";
      /* block
         comment
      */
      nested?: {
        code: string;
      };
    };
    """

    stripped = parser._strip_comments(ts_source)
    assert "remove this" not in stripped
    assert "comment" not in stripped
    assert "https://example.test//path" in stripped
    assert "/* keep me */" in stripped
    assert stripped.count("\n") == ts_source.count("\n")

    aliases = parse_exported_type_aliases(ts_source)
    properties = aliases["Demo"].properties
    assert properties is not None
    nested_property = properties["nested"]
    assert nested_property.inline_object is not None
    assert nested_property.inline_object.name == "Demo.nested"


def test_parse_object_alias_with_required_optional_and_inline_object_property() -> None:
    ts_source = """
    export type Parent = {
      id: string;
      count?: number;
      child: {
        name: string;
      };
    };
    """

    aliases = parse_exported_type_aliases(ts_source)
    parent = aliases["Parent"]
    assert parent.kind == "object"

    properties = parent.properties
    assert properties is not None
    assert properties["id"] == TsProperty(name="id", optional=False, type_expr="string")
    assert properties["count"] == TsProperty(name="count", optional=True, type_expr="number")

    child = properties["child"]
    assert child.inline_object is not None
    assert child.inline_object.name == "Parent.child"
    assert child.inline_object.properties == {
        "name": TsProperty(name="name", optional=False, type_expr="string"),
    }


def test_parse_union_aliases_for_string_literals_and_identifiers() -> None:
    ts_source = """
    export type StringUnion = "a" | "b";
    export type IdentifierUnion = Foo | Bar;
    """

    aliases = parse_exported_type_aliases(ts_source)

    assert aliases["StringUnion"].kind == "string_union"
    assert aliases["StringUnion"].string_literals == ("a", "b")
    assert aliases["IdentifierUnion"].kind == "identifier_union"
    assert aliases["IdentifierUnion"].union_members == ("Foo", "Bar")


def test_extract_exported_type_alias_rhs_raises_for_missing_alias() -> None:
    with pytest.raises(ValueError, match="Could not find exported type alias"):
        extract_exported_type_alias_rhs("export type Present = string;", "Missing")


def test_extract_exported_type_alias_rhs_raises_when_semicolon_is_missing() -> None:
    ts_source = "export type Broken = { value: string }"

    with pytest.raises(ValueError, match="terminating semicolon"):
        extract_exported_type_alias_rhs(ts_source, "Broken")


@pytest.mark.parametrize(
    "ts_source",
    [
        "export type Empty = ;",
        "export type Empty =   ;",
    ],
)
def test_parse_exported_type_aliases_rejects_empty_rhs(ts_source: str) -> None:
    with pytest.raises(ValueError, match="empty right-hand side"):
        parse_exported_type_aliases(ts_source)


@pytest.mark.parametrize(
    "rhs",
    [
        "Foo | 123",
        "`templated` | Foo",
    ],
)
def test_parse_exported_type_aliases_rejects_unsupported_union_member(rhs: str) -> None:
    ts_source = f"export type BadUnion = {rhs};"

    with pytest.raises(ValueError, match="unsupported union member"):
        parse_exported_type_aliases(ts_source)


def test_parse_exported_type_aliases_rejects_malformed_property() -> None:
    ts_source = "export type Broken = { foo string; };"

    with pytest.raises(ValueError, match="malformed property"):
        parse_exported_type_aliases(ts_source)


def test_parse_exported_type_aliases_rejects_empty_property_type() -> None:
    ts_source = "export type Broken = { foo: ; };"

    with pytest.raises(ValueError, match="empty type for property"):
        parse_exported_type_aliases(ts_source)


def test_parse_exported_type_aliases_rejects_unsupported_property_name() -> None:
    ts_source = "export type Broken = { foo-bar: string; };"

    with pytest.raises(ValueError, match="unsupported property name"):
        parse_exported_type_aliases(ts_source)


def test_extract_object_body_rejects_unbalanced_braces() -> None:
    with pytest.raises(ValueError, match="unbalanced braces"):
        parser._extract_object_body("Broken", "{ foo: string")


def test_parse_exported_type_aliases_rejects_object_trailing_expression() -> None:
    ts_source = "export type Broken = { foo: string } & Something;"

    with pytest.raises(ValueError, match="unsupported trailing expression"):
        parse_exported_type_aliases(ts_source)


def test_split_top_level_rejects_multi_character_delimiter() -> None:
    with pytest.raises(ValueError, match="single character"):
        parser._split_top_level("a|b", delimiter="||")


def test_find_top_level_rejects_multi_character_target() -> None:
    with pytest.raises(ValueError, match="single character"):
        parser._find_top_level("a:b", target="::")
