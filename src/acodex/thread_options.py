from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired

ApprovalMode: TypeAlias = Literal["never", "on-request", "on-failure", "untrusted"]
SandboxMode: TypeAlias = Literal["read-only", "workspace-write", "danger-full-access"]
ModelReasoningEffort: TypeAlias = Literal["minimal", "low", "medium", "high", "xhigh"]
WebSearchMode: TypeAlias = Literal["disabled", "cached", "live"]


class ThreadOptions(TypedDict):
    """Thread-level options applied to each turn."""

    model: NotRequired[str]
    """Model name override."""

    sandbox_mode: NotRequired[SandboxMode]
    """Sandbox mode for command execution."""

    working_directory: NotRequired[str]
    """Working directory used for the turn."""

    skip_git_repo_check: NotRequired[bool]
    """Whether to skip repository checks."""

    model_reasoning_effort: NotRequired[ModelReasoningEffort]
    """Requested model reasoning effort."""

    network_access_enabled: NotRequired[bool]
    """Whether network access is enabled in sandboxed execution."""

    web_search_mode: NotRequired[WebSearchMode]
    """Web search mode configuration."""

    web_search_enabled: NotRequired[bool]
    """Legacy web search enable/disable flag."""

    approval_policy: NotRequired[ApprovalMode]
    """Approval policy for tool and command execution."""

    additional_directories: NotRequired[list[str]]
    """Additional directories to add to the execution workspace."""
