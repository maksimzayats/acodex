from __future__ import annotations

import re

_EXPORT_BLOCK_PATTERN: re.Pattern[str] = re.compile(
    r"""
    export                     # export keyword
    \s+
    (?:type\s+)?               # optional 'type'
    \{                         # opening brace
    (?P<names>[^}]+)           # everything until closing brace
    \}                         # closing brace
    """,
    re.VERBOSE | re.MULTILINE,
)


def _parse_export_block(block: str) -> list[str]:
    results: list[str] = []

    for part in block.split(","):
        item: str = part.strip()
        if not item:
            continue

        # Handle aliasing: Foo as Bar -> export name is Bar
        if " as " in item:
            _, alias = item.split(" as ", 1)
            results.append(alias.strip())
        else:
            results.append(item)

    return results


def extract_exported_objects(ts_source: str) -> list[str]:
    """Extract all exported object names from TypeScript export blocks.

    This function looks for export statements of the form:
    export { Foo, Bar } from "./module";
    export type { Baz } from "./module";

    It captures the names of the exported objects (Foo, Bar, Baz) and returns them as a list.

    Returns:
        A list of exported object names.

    """
    exports: list[str] = []

    for match in _EXPORT_BLOCK_PATTERN.finditer(ts_source):
        names_block: str = match.group("names")
        exports.extend(_parse_export_block(names_block))

    return exports
