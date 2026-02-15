from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict

from acodex._internal.config import serialize_config_overrides, to_config_value
from acodex.types.codex_options import CodexConfigObject, CodexConfigValue
from acodex.types.thread_options import (
    ApprovalMode,
    ModelReasoningEffort,
    SandboxMode,
    WebSearchMode,
)
from acodex.types.turn_options import TurnSignal

if TYPE_CHECKING:
    from typing_extensions import NotRequired


_INTERNAL_ORIGINATOR_ENV: Final[str] = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"
_PYTHON_SDK_ORIGINATOR: Final[str] = "codex_sdk_py"


class CodexExecArgs(TypedDict):
    """Arguments for the exec layer.

    Set `signal` via `event.set()` to request cancellation. Use `threading.Event` in synchronous
    flows and `asyncio.Event` in asynchronous flows.
    """

    input: str
    base_url: NotRequired[str]
    api_key: NotRequired[str]
    thread_id: NotRequired[str | None]
    images: NotRequired[list[str]]
    model: NotRequired[str]
    sandbox_mode: NotRequired[SandboxMode]
    working_directory: NotRequired[str]
    additional_directories: NotRequired[list[str]]
    skip_git_repo_check: NotRequired[bool]
    output_schema_file: NotRequired[str]
    model_reasoning_effort: NotRequired[ModelReasoningEffort]
    signal: NotRequired[TurnSignal]
    network_access_enabled: NotRequired[bool]
    web_search_mode: NotRequired[WebSearchMode]
    web_search_enabled: NotRequired[bool]
    approval_policy: NotRequired[ApprovalMode]


@dataclass
class CodexExecCommand:
    """Structured representation of a Codex CLI command."""

    argv: list[str]
    env: dict[str, str]
    stdin: str
    signal: TurnSignal | None = None


class CodexExecCLICommandBuilder:
    def __init__(
        self,
        *,
        args: CodexExecArgs,
        config_overrides: CodexConfigObject | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> None:
        self._args = args
        self._config_overrides = config_overrides
        self._env_overrides = env_overrides

        self._command = CodexExecCommand(argv=[], env={}, stdin="")
        self._seen_args: set[str] = set()

    def build_command(self) -> CodexExecCommand:
        self._add_input()
        self._add_env()
        self._add_signal()

        self._add_initial_command()
        self._add_config_overrides()
        self._add_model()
        self._add_sandbox_mode()
        self._add_working_directory()
        self._add_additional_directories()
        self._add_skip_git_repo_check()
        self._add_output_schema_file()
        self._add_model_reasoning_effort()
        self._add_network_access_enabled()
        self._add_web_search_mode()
        self._add_approval_policy()
        self._add_thread_id()
        self._add_images()

        return self._command

    def _add_input(self) -> None:
        self._seen_args.add("input")

        stdin = self._args.get("input")
        if not stdin:
            return

        self._command.stdin = stdin

    def _add_env(self) -> None:
        env = dict(self._env_overrides) if self._env_overrides is not None else dict(os.environ)

        self._seen_args.add("base_url")
        base_url = self._args.get("base_url")
        if base_url:
            env["OPENAI_BASE_URL"] = base_url

        self._seen_args.add("api_key")
        api_key = self._args.get("api_key")
        if api_key:
            env["CODEX_API_KEY"] = api_key

        if _INTERNAL_ORIGINATOR_ENV not in env:
            env[_INTERNAL_ORIGINATOR_ENV] = _PYTHON_SDK_ORIGINATOR

        self._command.env = env

    def _add_signal(self) -> None:
        self._seen_args.add("signal")

        signal = self._args.get("signal")
        if not signal:
            return

        self._command.signal = signal

    def _add_initial_command(self) -> None:
        self._command.argv.append("exec")
        self._command.argv.append("--experimental-json")

    def _add_config_overrides(self) -> None:
        if self._config_overrides is None:
            return

        for override in serialize_config_overrides(self._config_overrides):
            self._command.argv.append("--config")
            self._command.argv.append(override)

    def _add_model(self) -> None:
        self._seen_args.add("model")

        model = self._args.get("model")
        if not model:
            return

        self._command.argv.append("--model")
        self._command.argv.append(str(model))

    def _add_sandbox_mode(self) -> None:
        self._seen_args.add("sandbox_mode")

        sandbox_mode = self._args.get("sandbox_mode")
        if not sandbox_mode:
            return

        self._command.argv.append("--sandbox")
        self._command.argv.append(str(sandbox_mode))

    def _add_working_directory(self) -> None:
        self._seen_args.add("working_directory")

        working_directory = self._args.get("working_directory")
        if not working_directory:
            return

        self._command.argv.append("--cd")
        self._command.argv.append(str(working_directory))

    def _add_additional_directories(self) -> None:
        self._seen_args.add("additional_directories")

        additional_directories = self._args.get("additional_directories")
        if not additional_directories:
            return

        for directory in additional_directories:
            self._command.argv.append("--add-dir")
            self._command.argv.append(str(directory))

    def _add_skip_git_repo_check(self) -> None:
        self._seen_args.add("skip_git_repo_check")

        skip_git_repo_check = self._args.get("skip_git_repo_check")
        if not skip_git_repo_check:
            return

        self._command.argv.append("--skip-git-repo-check")

    def _add_output_schema_file(self) -> None:
        self._seen_args.add("output_schema_file")

        output_schema_file = self._args.get("output_schema_file")
        if not output_schema_file:
            return

        self._command.argv.append("--output-schema")
        self._command.argv.append(str(output_schema_file))

    def _add_model_reasoning_effort(self) -> None:
        self._seen_args.add("model_reasoning_effort")

        model_reasoning_effort = self._args.get("model_reasoning_effort")
        if not model_reasoning_effort:
            return

        self._append_config_override("model_reasoning_effort", model_reasoning_effort)

    def _add_network_access_enabled(self) -> None:
        self._seen_args.add("network_access_enabled")

        network_access_enabled = self._args.get("network_access_enabled")
        if network_access_enabled is None:
            return

        self._append_config_override(
            "sandbox_workspace_write.network_access",
            network_access_enabled,
        )

    def _add_web_search_mode(self) -> None:
        self._seen_args.add("web_search_mode")
        self._seen_args.add("web_search_enabled")

        web_search_mode = self._args.get("web_search_mode")
        if web_search_mode:
            self._append_config_override("web_search", web_search_mode)
            return

        web_search_enabled = self._args.get("web_search_enabled")
        if web_search_enabled is True:
            self._append_config_override("web_search", "live")
        elif web_search_enabled is False:
            self._append_config_override("web_search", "disabled")

    def _add_approval_policy(self) -> None:
        self._seen_args.add("approval_policy")

        approval_policy = self._args.get("approval_policy")
        if not approval_policy:
            return

        self._append_config_override("approval_policy", approval_policy)

    def _add_thread_id(self) -> None:
        self._seen_args.add("thread_id")

        thread_id = self._args.get("thread_id")
        if not thread_id:
            return

        self._command.argv.append("resume")
        self._command.argv.append(thread_id)

    def _add_images(self) -> None:
        self._seen_args.add("images")

        images = self._args.get("images")
        if not images:
            return

        for image in images:
            self._command.argv.append("--image")
            self._command.argv.append(image)

    def _append_config_override(self, key: str, value: CodexConfigValue) -> None:
        config_value = to_config_value(value, key)
        self._command.argv.append("--config")
        self._command.argv.append(f"{key}={config_value}")
