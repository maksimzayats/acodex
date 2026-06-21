from __future__ import annotations

import json
from pathlib import Path

import pytest

from acodex.cli.tools import ToolArgumentsError, parse_tool_arguments


def test_parse_tool_arguments_from_long_options() -> None:
    assert parse_tool_arguments(
        [
            "--limit=1",
            "--query",
            "open issues",
            "--includeArchived",
            "--labels",
            '["bug", "p1"]',
            "--negative",
            "-1",
            "--empty=",
        ],
    ) == {
        "limit": 1,
        "query": "open issues",
        "includeArchived": True,
        "labels": ["bug", "p1"],
        "negative": -1,
        "empty": "",
    }


def test_parse_tool_arguments_from_json_sources(tmp_path: Path) -> None:
    args_file = tmp_path / "args.json"
    args_file.write_text(json.dumps({"payload": {"nested": True}}), encoding="utf-8")

    assert parse_tool_arguments(["--limit", "1"], args_json_file=args_file) == {
        "payload": {"nested": True},
        "limit": 1,
    }
    assert parse_tool_arguments([], args_json='{"limit": 2}') == {"limit": 2}


@pytest.mark.parametrize(
    "case",
    [
        ([], "[]", None, "JSON object"),
        ([], "{bad", None, "valid JSON"),
        (["limit=1"], None, None, "must use --name value"),
        (["--"], None, None, "must use --name value"),
        (["---limit"], None, None, "Invalid tool argument name"),
        (["--nested.value=1"], None, None, "Invalid tool argument name"),
        (["--limit=1", "--limit=2"], None, None, "Duplicate tool argument"),
        (["--limit=1"], '{"limit": 2}', None, "Duplicate tool argument"),
        (
            [],
            "{}",
            Path("args.json"),
            "cannot be used together",
        ),
    ],
)
def test_parse_tool_arguments_reports_invalid_input(
    case: tuple[list[str], str | None, Path | None, str],
) -> None:
    tokens, args_json, args_json_file, message = case
    with pytest.raises(ToolArgumentsError, match=message):
        parse_tool_arguments(tokens, args_json=args_json, args_json_file=args_json_file)


def test_parse_tool_arguments_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ToolArgumentsError, match="Could not read tool arguments"):
        parse_tool_arguments([], args_json_file=tmp_path)
