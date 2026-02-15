from __future__ import annotations

import re
from itertools import pairwise
from typing import cast

import pytest

from acodex._internal.exec import CodexExecArgs, CodexExecCLICommandBuilder
from acodex.types.codex_options import CodexConfigObject
from acodex.types.thread_options import ThreadOptions


def test_exec_cli_command_builder_dont_miss_args() -> None:
    builder = CodexExecCLICommandBuilder(args=CodexExecArgs(input="hello world"))

    command = builder.build_command()
    assert command.argv[0] == "exec"
    assert command.stdin == "hello world"

    exec_args = set(CodexExecArgs.__annotations__)
    assert exec_args - set(builder._seen_args) == set()


def test_exec_args_include_thead_args() -> None:
    thead_args = set(CodexExecArgs.__annotations__)
    thread_options_args = set(ThreadOptions.__annotations__)

    assert thread_options_args.issubset(thead_args)


def test_exec_builder_serializes_toml_config_overrides() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        config_overrides={
            "retry_budget": 3,
            "approval_policy": "never",
            "sandbox_workspace_write": {"network_access": True},
            "tool_rules": {"allow": ["git status", "git diff"]},
        },
    )

    command = builder.build_command()

    assert _collect_all_config_values(command.argv) == [
        "retry_budget=3",
        'approval_policy="never"',
        "sandbox_workspace_write.network_access=true",
        'tool_rules.allow=["git status", "git diff"]',
    ]


def test_exec_builder_serializes_empty_nested_object_override() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        config_overrides={"a": {"b": {}}},
    )

    command = builder.build_command()

    assert _collect_all_config_values(command.argv) == ["a.b={}"]


def test_exec_builder_skips_empty_top_level_config_overrides() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        config_overrides={},
    )

    command = builder.build_command()

    assert "--config" not in command.argv


@pytest.mark.parametrize(
    ("config_overrides", "error"),
    [
        (cast("CodexConfigObject", 1), "Codex config overrides must be a plain object"),
        (
            cast("CodexConfigObject", {"": 1}),
            "Codex config override keys must be non-empty strings",
        ),
        (
            cast("CodexConfigObject", {"numbers": [float("inf")]}),
            "Codex config override at numbers[0] must be a finite number",
        ),
        (
            cast("CodexConfigObject", {"root": None}),
            "Codex config override at root cannot be null",
        ),
        (
            cast("CodexConfigObject", {"root": (1, 2)}),
            "Unsupported Codex config override value at root: tuple",
        ),
    ],
)
def test_exec_builder_raises_for_invalid_config_overrides(
    config_overrides: CodexConfigObject,
    error: str,
) -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        config_overrides=config_overrides,
    )

    with pytest.raises(ValueError, match=re.escape(error)):
        builder.build_command()


def test_exec_builder_keeps_config_override_precedence_order() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world", approval_policy="on-request"),
        config_overrides={"approval_policy": "never"},
    )

    command = builder.build_command()
    approval_policy_overrides = _collect_config_values(command.argv, "approval_policy")

    assert approval_policy_overrides == [
        'approval_policy="never"',
        'approval_policy="on-request"',
    ]


def test_exec_builder_serializes_thread_config_flags_as_toml_values() -> None:
    builder = CodexExecCLICommandBuilder(
        args=cast(
            "CodexExecArgs",
            {
                "input": "hello world",
                "model_reasoning_effort": 'high"value',
                "network_access_enabled": True,
                "web_search_mode": 'live"value',
                "approval_policy": 'never"value',
            },
        ),
    )

    command = builder.build_command()

    assert _collect_all_config_values(command.argv) == [
        'model_reasoning_effort="high\\"value"',
        "sandbox_workspace_write.network_access=true",
        'web_search="live\\"value"',
        'approval_policy="never\\"value"',
    ]


def _collect_all_config_values(argv: list[str]) -> list[str]:
    return [value for key, value in pairwise(argv) if key == "--config"]


def _collect_config_values(argv: list[str], key: str) -> list[str]:
    prefix = f"{key}="
    return [value for value in _collect_all_config_values(argv) if value.startswith(prefix)]
