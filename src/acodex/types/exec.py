from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, TypedDict

from acodex.types.thread_options import (
    ApprovalMode,
    ModelReasoningEffort,
    SandboxMode,
    WebSearchMode,
)
from acodex.types.turn_options import TurnSignal

if TYPE_CHECKING:
    from typing_extensions import NotRequired


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


class CodexExecArg(str, Enum):
    INPUT = "input"
    BASE_URL = "base_url"
    API_KEY = "api_key"
    THREAD_ID = "thread_id"
    IMAGES = "images"
    MODEL = "model"
    SANDBOX_MODE = "sandbox_mode"
    WORKING_DIRECTORY = "working_directory"
    ADDITIONAL_DIRECTORIES = "additional_directories"
    SKIP_GIT_REPO_CHECK = "skip_git_repo_check"
    OUTPUT_SCHEMA_FILE = "output_schema_file"
    MODEL_REASONING_EFFORT = "model_reasoning_effort"
    SIGNAL = "signal"
    NETWORK_ACCESS_ENABLED = "network_access_enabled"
    WEB_SEARCH_MODE = "web_search_mode"
    WEB_SEARCH_ENABLED = "web_search_enabled"
    APPROVAL_POLICY = "approval_policy"
