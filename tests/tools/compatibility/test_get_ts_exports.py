from __future__ import annotations

from tools.compatibility.get_ts_exports import extract_exported_objects


def test_extract_exported_objects_handles_aliases_whitespace_and_empty_entries() -> None:
    ts_source = """
    export {
        Foo as FooAlias,
        Bar,
        ,
        Baz as BazAlias,,
    } from "./x";

    export type {
        Qux,
        Quux as QuuxAlias,
    } from "./y";
    """

    assert extract_exported_objects(ts_source) == [
        "FooAlias",
        "Bar",
        "BazAlias",
        "Qux",
        "QuuxAlias",
    ]


def test_extract_exported_objects_concatenates_multiple_blocks_in_appearance_order() -> None:
    ts_source = """
    export { First } from "./a";
    export type { Second } from "./b";
    export { Third as ThirdAlias } from "./c";
    """

    assert extract_exported_objects(ts_source) == ["First", "Second", "ThirdAlias"]
