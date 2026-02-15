from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from acodex._internal.exec import CodexExecArgs
from acodex._internal.locator import find_codex_path
from acodex.types.codex_options import CodexConfigObject


class CodexExec:
    """Execute `codex exec` calls for the synchronous client."""

    def __init__(
        self,
        *,
        executable_path: str | None = None,
        env: dict[str, str] | None = None,
        config_overrides: CodexConfigObject | None = None,
    ) -> None:
        self._executable_path = executable_path or find_codex_path()
        self._env = env
        self._config_overrides = config_overrides

    def run(self, args: CodexExecArgs) -> Iterator[str]:
        """Run Codex and stream JSONL lines."""
        raise NotImplementedError(args)


class AsyncCodexExec:
    """Execute `codex exec` calls for the asynchronous client."""

    def __init__(
        self,
        *,
        executable_path: str | None = None,
        env: dict[str, str] | None = None,
        config_overrides: CodexConfigObject | None = None,
    ) -> None:
        self._executable_path = executable_path or find_codex_path()
        self._env = env
        self._config_overrides = config_overrides

    async def run(self, args: CodexExecArgs) -> AsyncIterator[str]:
        """Run Codex and stream JSONL lines asynchronously."""
        raise NotImplementedError(args)
