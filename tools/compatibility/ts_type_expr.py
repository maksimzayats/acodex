from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Final, Literal

_IDENT_START_CHARS: Final[str] = "_$ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_IDENT_CHARS: Final[str] = _IDENT_START_CHARS + string.digits


@dataclass(frozen=True, slots=True)
class TsPrimitive:
    name: Literal["string", "number", "boolean", "unknown", "null"]


@dataclass(frozen=True, slots=True)
class TsIdentifier:
    name: str


@dataclass(frozen=True, slots=True)
class TsStringLiteral:
    value: str


@dataclass(frozen=True, slots=True)
class TsArray:
    element: TsTypeExpr


@dataclass(frozen=True, slots=True)
class TsUnion:
    members: tuple[TsTypeExpr, ...]


@dataclass(frozen=True, slots=True)
class TsGeneric:
    name: str
    args: tuple[TsTypeExpr, ...]


@dataclass(frozen=True, slots=True)
class TsObjectProperty:
    name: str
    optional: bool
    type_expr: TsTypeExpr


@dataclass(frozen=True, slots=True)
class TsIndexSignature:
    key_name: str
    key_type: TsTypeExpr
    value_type: TsTypeExpr


@dataclass(frozen=True, slots=True)
class TsObject:
    properties: tuple[TsObjectProperty, ...]
    index_signature: TsIndexSignature | None = None


TsTypeExpr = TsPrimitive | TsIdentifier | TsStringLiteral | TsArray | TsUnion | TsGeneric | TsObject


TokenKind = Literal["IDENT", "STRING", "SYMBOL", "EOF"]
_IDENT: Final[TokenKind] = "IDENT"
_STRING: Final[TokenKind] = "STRING"
_SYMBOL: Final[TokenKind] = "SYMBOL"
_EOF: Final[TokenKind] = "EOF"


@dataclass(frozen=True, slots=True)
class _Token:
    kind: TokenKind
    value: str
    index: int


class _Tokenizer:
    def __init__(self, text: str) -> None:
        self._text = text
        self._index = 0
        self._peeked: _Token | None = None

    def peek(self) -> _Token:
        if self._peeked is None:
            self._peeked = self._next_token()
        return self._peeked

    def pop(self) -> _Token:
        token = self.peek()
        self._peeked = None
        return token

    def expect_symbol(self, symbol: str) -> None:
        token = self.pop()
        if token.kind != _SYMBOL or token.value != symbol:
            msg = f"Expected symbol {symbol!r} at {token.index}, got {token.value!r}"
            raise ValueError(msg)

    def _next_token(self) -> _Token:
        text = self._text
        length = len(text)
        while self._index < length and text[self._index].isspace():
            self._index += 1

        if self._index >= length:
            return _Token(kind=_EOF, value="", index=self._index)

        start = self._index
        char = text[self._index]

        if char in {"'", '"'}:
            return self._read_string()

        if char in _IDENT_START_CHARS:
            return self._read_ident()

        self._index += 1
        return _Token(kind=_SYMBOL, value=char, index=start)

    def _read_ident(self) -> _Token:
        start = self._index
        text = self._text
        length = len(text)
        self._index += 1
        while self._index < length and text[self._index] in _IDENT_CHARS:
            self._index += 1
        return _Token(kind=_IDENT, value=text[start : self._index], index=start)

    def _read_string(self) -> _Token:
        start = self._index
        text = self._text
        quote = text[self._index]
        self._index += 1
        value_chars: list[str] = []
        escaped = False
        while self._index < len(text):
            char = text[self._index]
            self._index += 1
            if escaped:
                value_chars.append(char)
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                return _Token(kind=_STRING, value="".join(value_chars), index=start)
            value_chars.append(char)
        msg = f"Unterminated string literal at index {start}"
        raise ValueError(msg)


class _Parser:
    def __init__(self, tokenizer: _Tokenizer) -> None:
        self._toks = tokenizer

    def parse(self) -> TsTypeExpr:
        while True:
            token = self._toks.peek()
            if token.kind == _SYMBOL and token.value == "|":
                self._toks.pop()
                continue
            break
        expr = self._parse_union()
        token = self._toks.peek()
        if token.kind != _EOF:
            msg = f"Unexpected token {token.value!r} at {token.index}"
            raise ValueError(msg)
        return expr

    def _parse_union(self) -> TsTypeExpr:
        members: list[TsTypeExpr] = [self._parse_postfix()]
        while True:
            token = self._toks.peek()
            if token.kind == _SYMBOL and token.value == "|":
                self._toks.pop()
                members.append(self._parse_postfix())
                continue
            break
        if len(members) == 1:
            return members[0]
        flattened: list[TsTypeExpr] = []
        for member in members:
            if isinstance(member, TsUnion):
                flattened.extend(member.members)
            else:
                flattened.append(member)
        return TsUnion(members=tuple(flattened))

    def _parse_postfix(self) -> TsTypeExpr:
        expr = self._parse_primary()
        while True:
            token = self._toks.peek()
            if token.kind == _SYMBOL and token.value == "[":
                self._toks.pop()
                self._toks.expect_symbol("]")
                expr = TsArray(element=expr)
                continue
            break
        return expr

    def _parse_primary(self) -> TsTypeExpr:
        token = self._toks.pop()
        if token.kind == _STRING:
            return TsStringLiteral(value=token.value)

        if token.kind == _IDENT:
            if token.value in {"string", "number", "boolean", "unknown", "null"}:
                return TsPrimitive(name=token.value)  # type: ignore[arg-type]

            ident_expr: TsTypeExpr = TsIdentifier(name=token.value)
            next_token = self._toks.peek()
            if next_token.kind == _SYMBOL and next_token.value == "<":
                ident_expr = self._parse_generic(token.value)
            return ident_expr

        if token.kind == _SYMBOL and token.value == "{":
            return self._parse_object_body()

        if token.kind == _SYMBOL and token.value == "(":
            inner = self._parse_union()
            self._toks.expect_symbol(")")
            return inner

        msg = f"Unexpected token {token.value!r} at {token.index}"
        raise ValueError(msg)

    def _parse_generic(self, name: str) -> TsGeneric:
        self._toks.expect_symbol("<")
        args: list[TsTypeExpr] = []
        while True:
            args.append(self._parse_union())
            token = self._toks.peek()
            if token.kind == _SYMBOL and token.value == ",":
                self._toks.pop()
                continue
            break
        self._toks.expect_symbol(">")
        return TsGeneric(name=name, args=tuple(args))

    def _parse_object_body(self) -> TsObject:
        properties: list[TsObjectProperty] = []
        index_signature: TsIndexSignature | None = None

        while True:
            token = self._toks.peek()
            if token.kind == _EOF:
                msg = "Unterminated object type (missing '}')"
                raise ValueError(msg)
            if token.kind == _SYMBOL and token.value == "}":
                self._toks.pop()
                break
            if token.kind == _SYMBOL and token.value in {";", ","}:
                self._toks.pop()
                continue

            if token.kind == _SYMBOL and token.value == "[":
                if index_signature is not None:
                    msg = "Object type contains multiple index signatures"
                    raise ValueError(msg)
                index_signature = self._parse_index_signature()
            else:
                properties.append(self._parse_object_property())

            token = self._toks.peek()
            if token.kind == _SYMBOL and token.value in {";", ","}:
                self._toks.pop()

        return TsObject(properties=tuple(properties), index_signature=index_signature)

    def _parse_index_signature(self) -> TsIndexSignature:
        self._toks.expect_symbol("[")
        name_token = self._toks.pop()
        if name_token.kind != _IDENT:
            msg = f"Expected index signature name at {name_token.index}"
            raise ValueError(msg)
        self._toks.expect_symbol(":")
        key_type = self._parse_union()
        self._toks.expect_symbol("]")
        self._toks.expect_symbol(":")
        value_type = self._parse_union()
        return TsIndexSignature(
            key_name=name_token.value,
            key_type=key_type,
            value_type=value_type,
        )

    def _parse_object_property(self) -> TsObjectProperty:
        name_token = self._toks.pop()
        if name_token.kind != _IDENT:
            msg = f"Expected property name at {name_token.index}"
            raise ValueError(msg)
        optional = False
        token = self._toks.peek()
        if token.kind == _SYMBOL and token.value == "?":
            self._toks.pop()
            optional = True
        self._toks.expect_symbol(":")
        type_expr = self._parse_union()
        return TsObjectProperty(name=name_token.value, optional=optional, type_expr=type_expr)


def parse_ts_type_expr(expr: str) -> TsTypeExpr:
    """Parse a small subset of TypeScript type expressions used by the vendored SDK.

    Returns:
        Parsed type expression AST.

    """
    tokenizer = _Tokenizer(expr)
    parser = _Parser(tokenizer)
    return parser.parse()
