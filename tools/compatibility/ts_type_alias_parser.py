from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

_ALIAS_DECLARATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bexport\s+type\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=",
    re.MULTILINE,
)
_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_STRING_QUOTES: Final[frozenset[str]] = frozenset({'"', "'", "`"})
_MIN_STRING_LITERAL_LENGTH: Final[int] = 2


@dataclass(frozen=True, slots=True)
class TsAlias:
    name: str
    kind: Literal["object", "string_union", "identifier_union"]
    properties: dict[str, TsProperty] | None = None
    string_literals: tuple[str, ...] | None = None
    union_members: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TsProperty:
    name: str
    optional: bool
    type_expr: str
    inline_object: TsAlias | None = None


@dataclass(slots=True)
class _CommentState:
    in_string: str | None = None
    escaped: bool = False

    def consume_string_char(self, char: str) -> None:
        if self.escaped:
            self.escaped = False
            return

        if char == "\\":
            self.escaped = True
            return

        if char == self.in_string:
            self.in_string = None


@dataclass(slots=True)
class _DepthState:
    brace_depth: int = 0
    bracket_depth: int = 0
    paren_depth: int = 0
    in_string: str | None = None
    escaped: bool = False

    def consume_char(self, char: str) -> None:
        if self.in_string is not None:
            self._consume_string_char(char)
            return

        if char in _STRING_QUOTES:
            self.in_string = char
            return

        self.brace_depth += _depth_delta(char, opening="{", closing="}")
        self.bracket_depth += _depth_delta(char, opening="[", closing="]")
        self.paren_depth += _depth_delta(char, opening="(", closing=")")

    def _consume_string_char(self, char: str) -> None:
        if self.escaped:
            self.escaped = False
            return

        if char == "\\":
            self.escaped = True
            return

        if char == self.in_string:
            self.in_string = None


def parse_exported_type_aliases(ts_source: str) -> dict[str, TsAlias]:
    stripped_source = _strip_comments(ts_source)
    aliases: dict[str, TsAlias] = {}

    for match in _ALIAS_DECLARATION_PATTERN.finditer(stripped_source):
        alias_name = match.group("name")
        alias_rhs, _ = _capture_rhs_until_semicolon(stripped_source, start=match.end())
        aliases[alias_name] = _parse_alias(alias_name, alias_rhs.strip())

    return aliases


def _strip_comments(source: str) -> str:
    result: list[str] = []
    index = 0
    state = _CommentState()

    while index < len(source):
        if state.in_string is not None:
            char = source[index]
            result.append(char)
            state.consume_string_char(char)
            index += 1
            continue

        if _starts_block_comment(source, index):
            index = _skip_block_comment(source, index, result=result)
            continue

        if _starts_line_comment(source, index):
            index = _skip_line_comment(source, index)
            continue

        char = source[index]
        if char in _STRING_QUOTES:
            state.in_string = char
        result.append(char)
        index += 1

    return "".join(result)


def _capture_rhs_until_semicolon(source: str, *, start: int) -> tuple[str, int]:
    state = _DepthState()
    for index in range(start, len(source)):
        char = source[index]
        state.consume_char(char)
        if char == ";" and _is_top_level(state):
            return source[start:index], index + 1

    msg = f"Could not find terminating semicolon for alias at index {start}"
    raise ValueError(msg)


def _parse_alias(alias_name: str, rhs: str) -> TsAlias:
    if rhs.startswith("{"):
        return TsAlias(
            name=alias_name,
            kind="object",
            properties=_parse_object_properties(alias_name, rhs),
        )

    union_tokens = [
        token.strip() for token in _split_top_level(rhs, delimiter="|") if token.strip()
    ]
    if not union_tokens:
        msg = f"Alias {alias_name} has an empty right-hand side"
        raise ValueError(msg)

    string_literals: list[str] = []
    for token in union_tokens:
        parsed = _parse_string_literal(token)
        if parsed is None:
            break
        string_literals.append(parsed)
    else:
        return TsAlias(
            name=alias_name,
            kind="string_union",
            string_literals=tuple(string_literals),
        )

    for token in union_tokens:
        if not _IDENTIFIER_PATTERN.fullmatch(token):
            msg = f"Alias {alias_name} includes unsupported union member: {token!r}"
            raise ValueError(msg)

    return TsAlias(
        name=alias_name,
        kind="identifier_union",
        union_members=tuple(union_tokens),
    )


def _parse_object_properties(alias_name: str, object_expr: str) -> dict[str, TsProperty]:
    object_body = _extract_object_body(alias_name, object_expr)
    raw_properties = _split_top_level(object_body, delimiter=";")

    properties: dict[str, TsProperty] = {}
    for raw_property in raw_properties:
        stripped_property = raw_property.strip()
        if not stripped_property:
            continue

        property_name, optional, type_expr = _parse_property(alias_name, stripped_property)
        inline_object: TsAlias | None = None
        if type_expr.lstrip().startswith("{"):
            inline_object = TsAlias(
                name=f"{alias_name}.{property_name}",
                kind="object",
                properties=_parse_object_properties(f"{alias_name}.{property_name}", type_expr),
            )

        properties[property_name] = TsProperty(
            name=property_name,
            optional=optional,
            type_expr=type_expr,
            inline_object=inline_object,
        )

    return properties


def _extract_object_body(alias_name: str, object_expr: str) -> str:
    stripped_expr = object_expr.strip()
    if not stripped_expr.startswith("{"):
        msg = f"Alias {alias_name} is expected to start with '{{'"
        raise ValueError(msg)

    state = _DepthState()
    closing_index: int | None = None

    for index, char in enumerate(stripped_expr):
        previous_brace_depth = state.brace_depth
        state.consume_char(char)
        if (
            char == "}"
            and previous_brace_depth == 1
            and state.brace_depth == 0
            and state.in_string is None
        ):
            closing_index = index
            break

    if closing_index is None:
        msg = f"Alias {alias_name} object has unbalanced braces"
        raise ValueError(msg)

    trailing_text = stripped_expr[closing_index + 1 :].strip()
    if trailing_text:
        msg = f"Alias {alias_name} object has unsupported trailing expression: {trailing_text!r}"
        raise ValueError(msg)

    return stripped_expr[1:closing_index]


def _parse_property(alias_name: str, raw_property: str) -> tuple[str, bool, str]:
    separator_index = _find_top_level(raw_property, target=":")
    if separator_index == -1:
        msg = f"Alias {alias_name} contains malformed property: {raw_property!r}"
        raise ValueError(msg)

    raw_name = raw_property[:separator_index].strip()
    raw_type_expr = raw_property[separator_index + 1 :].strip()
    if not raw_type_expr:
        msg = f"Alias {alias_name} contains empty type for property: {raw_name!r}"
        raise ValueError(msg)

    optional = raw_name.endswith("?")
    name = raw_name[:-1].strip() if optional else raw_name
    if not _IDENTIFIER_PATTERN.fullmatch(name):
        msg = f"Alias {alias_name} contains unsupported property name: {name!r}"
        raise ValueError(msg)

    return name, optional, raw_type_expr


def _split_top_level(text: str, *, delimiter: str) -> list[str]:
    if len(delimiter) != 1:
        msg = "Delimiter must be a single character"
        raise ValueError(msg)

    parts: list[str] = []
    start_index = 0
    state = _DepthState()

    for index, char in enumerate(text):
        state.consume_char(char)
        if char == delimiter and _is_top_level(state):
            parts.append(text[start_index:index])
            start_index = index + 1

    parts.append(text[start_index:])
    return parts


def _find_top_level(text: str, *, target: str) -> int:
    if len(target) != 1:
        msg = "Target must be a single character"
        raise ValueError(msg)

    state = _DepthState()

    for index, char in enumerate(text):
        state.consume_char(char)
        if char == target and _is_top_level(state):
            return index

    return -1


def _parse_string_literal(token: str) -> str | None:
    stripped_token = token.strip()
    if len(stripped_token) < _MIN_STRING_LITERAL_LENGTH:
        return None

    quote = stripped_token[0]
    if quote not in {'"', "'"} or stripped_token[-1] != quote:
        return None

    return stripped_token[1:-1]


def _starts_block_comment(source: str, index: int) -> bool:
    return source[index : index + 2] == "/*"


def _starts_line_comment(source: str, index: int) -> bool:
    return source[index : index + 2] == "//"


def _skip_block_comment(source: str, index: int, *, result: list[str]) -> int:
    index += 2
    while index < len(source):
        if source[index : index + 2] == "*/":
            return index + 2
        if source[index] == "\n":
            result.append("\n")
        index += 1
    return index


def _skip_line_comment(source: str, index: int) -> int:
    index += 2
    while index < len(source) and source[index] != "\n":
        index += 1
    return index


def _depth_delta(char: str, *, opening: str, closing: str) -> int:
    if char == opening:
        return 1
    if char == closing:
        return -1
    return 0


def _is_top_level(state: _DepthState) -> bool:
    return (
        state.in_string is None
        and state.brace_depth == 0
        and state.bracket_depth == 0
        and state.paren_depth == 0
    )
