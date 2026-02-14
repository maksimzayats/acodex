from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired

ApprovalMode: TypeAlias = Literal["never", "on-request", "on-failure", "untrusted"]
SandboxMode: TypeAlias = Literal["read-only", "workspace-write", "danger-full-access"]
ModelReasoningEffort: TypeAlias = Literal["minimal", "low", "medium", "high", "xhigh"]
WebSearchMode: TypeAlias = Literal["disabled", "cached", "live"]


class ThreadOptions(TypedDict):
    model: NotRequired[str]
    sandbox_mode: NotRequired[SandboxMode]
    working_directory: NotRequired[str]
    skip_git_repo_check: NotRequired[bool]
    model_reasoning_effort: NotRequired[ModelReasoningEffort]
    network_access_enabled: NotRequired[bool]
    web_search_mode: NotRequired[WebSearchMode]
    web_search_enabled: NotRequired[bool]
    approval_policy: NotRequired[ApprovalMode]
    additional_directories: NotRequired[list[str]]
