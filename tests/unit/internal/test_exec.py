from __future__ import annotations

import re
import threading
from itertools import pairwise
from typing import cast

import pytest

from acodex._internal.exec import (
    _INTERNAL_ORIGINATOR_ENV,
    _PYTHON_SDK_ORIGINATOR,
    CodexExecArgs,
    CodexExecCLICommandBuilder,
    build_exec_args,
)
from acodex.exceptions import CodexConfigError
from acodex.types.codex_options import CodexConfigObject
from acodex.types.input import UserInputLocalImage, UserInputText
from acodex.types.thread_options import ThreadOptions


def test_exec_cli_command_builder_dont_miss_args() -> None:
    builder = CodexExecCLICommandBuilder(args=CodexExecArgs(input="hello world"))

    command = builder.build_command()
    assert command.argv[0] == "exec"
    assert command.stdin == "hello world"

    exec_args = set(CodexExecArgs.__annotations__)
    assert exec_args - set(builder._seen_args) == set()


def test_exec_builder_allows_empty_input_string() -> None:
    builder = CodexExecCLICommandBuilder(args=CodexExecArgs(input=""))

    command = builder.build_command()

    assert not command.stdin
    assert command.argv[:2] == ["exec", "--experimental-json"]


def test_exec_builder_sets_base_url_and_api_key_env() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello", base_url="https://example.test", api_key="key-123"),
        env_overrides={},
    )

    command = builder.build_command()

    assert command.env["OPENAI_BASE_URL"] == "https://example.test"
    assert command.env["CODEX_API_KEY"] == "key-123"


def test_exec_builder_forwards_signal_object() -> None:
    signal = threading.Event()
    builder = CodexExecCLICommandBuilder(args=CodexExecArgs(input="hello", signal=signal))

    command = builder.build_command()

    assert command.signal is signal


def test_exec_builder_adds_exec_flags_model_sandbox_cd_add_dir_skip_git_schema() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(
            input="hello",
            model="gpt-5",
            sandbox_mode="workspace-write",
            working_directory="/workspace",
            additional_directories=["/extra/a", "/extra/b"],
            skip_git_repo_check=True,
            output_schema_file="/workspace/schema.json",
        ),
    )

    command = builder.build_command()

    assert _extract_flag_values(command.argv, "--model") == ["gpt-5"]
    assert _extract_flag_values(command.argv, "--sandbox") == ["workspace-write"]
    assert _extract_flag_values(command.argv, "--cd") == ["/workspace"]
    assert _extract_flag_values(command.argv, "--add-dir") == ["/extra/a", "/extra/b"]
    assert "--skip-git-repo-check" in command.argv
    assert _extract_flag_values(command.argv, "--output-schema") == ["/workspace/schema.json"]


def test_exec_builder_web_search_enabled_true_false_sets_config_override() -> None:
    enabled_builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello", web_search_enabled=True),
    )
    disabled_builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello", web_search_enabled=False),
    )

    enabled_command = enabled_builder.build_command()
    disabled_command = disabled_builder.build_command()

    assert _collect_config_values(enabled_command.argv, "web_search") == ['web_search="live"']
    assert _collect_config_values(disabled_command.argv, "web_search") == [
        'web_search="disabled"',
    ]


def test_exec_builder_places_resume_args_before_image_args() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(
            input="hello",
            thread_id="thread-1",
            images=["/images/a.png"],
        ),
    )

    command = builder.build_command()

    assert command.argv.index("resume") < command.argv.index("--image")


def test_exec_args_include_thead_args() -> None:
    thead_args = set(CodexExecArgs.__annotations__)
    thread_options_args = set(ThreadOptions.__annotations__)

    assert thread_options_args.issubset(thead_args)


def test_build_exec_args_includes_normalized_input_thread_metadata_and_turn_options() -> None:
    signal = threading.Event()
    args = build_exec_args(
        input=[
            UserInputText(text="hello"),
            UserInputLocalImage(path="/images/one.png"),
            UserInputText(text="world"),
        ],
        options={},
        thread_options={},
        thread_id="thread-123",
        turn_options={"signal": signal},
        output_schema_path="/schemas/schema.json",
    )

    assert args["input"] == "hello\n\nworld"
    assert args["images"] == ["/images/one.png"]
    assert args["thread_id"] == "thread-123"
    assert args["signal"] is signal
    assert args["output_schema_file"] == "/schemas/schema.json"


def test_build_exec_args_unpacks_thread_options_with_none_values() -> None:
    thread_options = cast(
        "ThreadOptions",
        {
            "model": None,
            "skip_git_repo_check": None,
            "network_access_enabled": None,
        },
    )

    args = build_exec_args(
        input="hello world",
        options={},
        thread_options=thread_options,
        thread_id=None,
        turn_options={},
        output_schema_path=None,
    )
    args_dict = cast("dict[str, object]", args)

    assert args_dict["model"] is None
    assert args_dict["skip_git_repo_check"] is None
    assert args_dict["network_access_enabled"] is None


def test_build_exec_args_includes_base_url_and_api_key_from_codex_options() -> None:
    args = build_exec_args(
        input="hello world",
        options={"base_url": "https://example.test", "api_key": "key-123"},
        thread_options={},
        thread_id=None,
        turn_options={},
        output_schema_path=None,
    )

    assert args["base_url"] == "https://example.test"
    assert args["api_key"] == "key-123"


def test_exec_builder_serializes_config_overrides() -> None:
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


def test_exec_builder_serializes_numeric_overrides_with_js_number_parity() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        config_overrides={
            "small": 1e-7,
            "threshold": 1e-6,
        },
    )

    command = builder.build_command()

    assert _collect_all_config_values(command.argv) == [
        "small=1e-7",
        "threshold=0.000001",
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

    with pytest.raises(CodexConfigError, match=re.escape(error)):
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


def test_exec_builder_serializes_thread_config_flags_as_config_values() -> None:
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


def test_exec_builder_does_not_inherit_process_env_when_empty_env_overrides_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_ENV_SHOULD_NOT_LEAK", "leak")

    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        env_overrides={},
    )

    command = builder.build_command()

    assert command.env == {
        _INTERNAL_ORIGINATOR_ENV: _PYTHON_SDK_ORIGINATOR,
    }


def test_exec_builder_keeps_existing_internal_originator_env_value() -> None:
    builder = CodexExecCLICommandBuilder(
        args=CodexExecArgs(input="hello world"),
        env_overrides={_INTERNAL_ORIGINATOR_ENV: "custom-originator"},
    )

    command = builder.build_command()

    assert command.env[_INTERNAL_ORIGINATOR_ENV] == "custom-originator"


def _collect_all_config_values(argv: list[str]) -> list[str]:
    return [value for key, value in pairwise(argv) if key == "--config"]


def _extract_flag_values(argv: list[str], flag: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(argv):
        if argv[index] == flag and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 2
            continue
        index += 1
    return values


def _collect_config_values(argv: list[str], key: str) -> list[str]:
    prefix = f"{key}="
    return [value for value in _collect_all_config_values(argv) if value.startswith(prefix)]
