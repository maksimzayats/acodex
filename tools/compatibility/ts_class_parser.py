from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

_CLASS_DECLARATION_TEMPLATE: Final[str] = r"\bexport\s+class\s+{name}\b"

_GETTER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    \s*
    (?:public\s+)?
    get
    \s+
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    \s*
    \(
    """,
    re.VERBOSE,
)
_METHOD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    ^
    \s*
    (?:public\s+)?
    (?:async\s+)?
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    \s*
    \(
    """,
    re.VERBOSE,
)

_STRING_QUOTES: Final[frozenset[str]] = frozenset({'"', "'", "`"})


@dataclass(frozen=True, slots=True)
class ParsedClassSurface:
    methods: tuple[str, ...]
    getters: tuple[str, ...]


@dataclass(slots=True)
class _DepthState:
    brace_depth: int = 0
    in_string: str | None = None
    escaped: bool = False

    def consume_char(self, char: str) -> None:
        if self.in_string is not None:
            self._consume_string_char(char)
            return

        if char in _STRING_QUOTES:
            self.in_string = char
            return

        if char == "{":
            self.brace_depth += 1
        elif char == "}":
            self.brace_depth -= 1

    def _consume_string_char(self, char: str) -> None:
        if self.escaped:
            self.escaped = False
            return

        if char == "\\":
            self.escaped = True
            return

        if char == self.in_string:
            self.in_string = None


def extract_exported_class_members(ts_source: str, class_name: str) -> ParsedClassSurface:
    """Extract a narrow public surface from an exported TypeScript class.

    This parser intentionally supports only the patterns present in the vendored TypeScript SDK.
    It identifies public instance methods and getters, excluding private/protected members and
    constructors.

    Returns:
        Parsed public methods and getters for the exported class.

    Raises:
        ValueError: When the exported class cannot be found or parsed.

    """
    stripped_source = _strip_comments(ts_source)
    class_decl = re.compile(
        _CLASS_DECLARATION_TEMPLATE.format(name=re.escape(class_name)),
        re.MULTILINE,
    )
    match = class_decl.search(stripped_source)
    if match is None:
        msg = f"Could not find exported class: {class_name!r}"
        raise ValueError(msg)

    open_brace = stripped_source.find("{", match.end())
    if open_brace == -1:
        msg = f"Could not find opening brace for class {class_name!r}"
        raise ValueError(msg)

    class_body = _capture_balanced_braces(stripped_source, start=open_brace)
    methods: list[str] = []
    getters: list[str] = []

    state = _DepthState()
    for line in class_body.splitlines():
        stripped_line = line.strip()
        if state.brace_depth != 0 or not stripped_line:
            _consume_line(state, line)
            continue

        if stripped_line.startswith(("private ", "protected ", "constructor", "static ")):
            _consume_line(state, line)
            continue

        getter_match = _GETTER_PATTERN.match(stripped_line)
        if getter_match is not None:
            getters.append(getter_match.group("name"))
            _consume_line(state, line)
            continue

        method_match = _METHOD_PATTERN.match(stripped_line)
        if method_match is not None:
            name = method_match.group("name")
            if name != "constructor":
                methods.append(name)

        _consume_line(state, line)

    return ParsedClassSurface(methods=tuple(methods), getters=tuple(getters))


def _consume_line(state: _DepthState, line: str) -> None:
    for char in f"{line}\n":
        state.consume_char(char)


def _capture_balanced_braces(source: str, *, start: int) -> str:
    state = _DepthState()
    for index in range(start, len(source)):
        char = source[index]
        previous_depth = state.brace_depth
        state.consume_char(char)
        if previous_depth == 1 and state.brace_depth == 0 and state.in_string is None:
            return source[start + 1 : index]
    msg = f"Could not find closing brace starting at index {start}"
    raise ValueError(msg)


def _strip_comments(source: str) -> str:
    result: list[str] = []
    index = 0
    in_string: str | None = None
    escaped = False

    while index < len(source):
        if in_string is not None:
            index, in_string, escaped = _consume_string(
                source,
                index=index,
                in_string=in_string,
                escaped=escaped,
                result=result,
            )
            continue

        if source[index : index + 2] == "/*":
            index = _skip_block_comment(source, index=index, result=result)
            continue

        if source[index : index + 2] == "//":
            index = _skip_line_comment(source, index=index)
            continue

        char = source[index]
        if char in _STRING_QUOTES:
            in_string = char
        result.append(char)
        index += 1

    return "".join(result)


def _consume_string(
    source: str,
    *,
    index: int,
    in_string: str,
    escaped: bool,
    result: list[str],
) -> tuple[int, str | None, bool]:
    char = source[index]
    result.append(char)
    if escaped:
        return index + 1, in_string, False
    if char == "\\":
        return index + 1, in_string, True
    if char == in_string:
        return index + 1, None, False
    return index + 1, in_string, False


def _skip_block_comment(source: str, *, index: int, result: list[str]) -> int:
    index += 2
    while index < len(source):
        if source[index : index + 2] == "*/":
            return index + 2
        if source[index] == "\n":
            result.append("\n")
        index += 1
    return index


def _skip_line_comment(source: str, *, index: int) -> int:
    index += 2
    while index < len(source) and source[index] != "\n":
        index += 1
    return index
