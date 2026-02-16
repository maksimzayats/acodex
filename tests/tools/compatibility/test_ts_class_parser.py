from __future__ import annotations

import pytest

from tools.compatibility.ts_class_parser import ParsedClassSurface, extract_exported_class_members


def test_extract_exported_class_members_happy_path_with_nested_blocks_comments_and_strings() -> (
    None
):
    ts_source = """
    export class Codex {
      /* Comment with braces and fake members:
         get hidden() { return "x"; }
      */
      public async run(input: string) {
        if (input) {
          fakeMethod() {}
          const marker = "} // /*";
        }
      }

      get name() {
        return "codex";
      }

      private secret() {}
      protected guard() {}
      constructor() {}
      static build() {}
      public ping() {}
      // get notAGetter() {}
    }
    """

    assert extract_exported_class_members(ts_source, "Codex") == ParsedClassSurface(
        methods=("run", "ping"),
        getters=("name",),
    )


def test_extract_exported_class_members_raises_when_exported_class_not_found() -> None:
    with pytest.raises(ValueError, match="Could not find exported class"):
        extract_exported_class_members("export class Other {}", "Codex")


def test_extract_exported_class_members_raises_when_opening_brace_is_missing() -> None:
    ts_source = """
    export class Codex
    const value = 1;
    """

    with pytest.raises(ValueError, match="opening brace"):
        extract_exported_class_members(ts_source, "Codex")


def test_extract_exported_class_members_raises_when_closing_brace_is_missing() -> None:
    ts_source = "export class Codex { public run() { if (true) { return; }"

    with pytest.raises(ValueError, match="closing brace"):
        extract_exported_class_members(ts_source, "Codex")
