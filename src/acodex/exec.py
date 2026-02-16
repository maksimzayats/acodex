from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator

from acodex._internal.exec import CodexExecArgs, CodexExecCLICommandBuilder
from acodex._internal.locator import find_codex_path
from acodex._internal.process_runner import AsyncCodexProcessRunner, SyncCodexProcessRunner
from acodex.types.codex_options import CodexConfigObject

logger = logging.getLogger(__name__)


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
        """Run Codex and stream JSONL lines.

        Yields:
            JSONL line payloads emitted by the Codex CLI.

        """
        command = CodexExecCLICommandBuilder(
            args=args,
            config_overrides=self._config_overrides,
            env_overrides=self._env,
        ).build_command()
        logger.debug("Running Codex CLI command: %s", command.argv)
        runner = SyncCodexProcessRunner(executable_path=self._executable_path)
        yield from runner.stream_lines(command)
        logger.debug("Finished Codex CLI command: %s", command.argv)


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
        """Run Codex and stream JSONL lines asynchronously.

        Yields:
            JSONL line payloads emitted by the Codex CLI.

        """
        command = CodexExecCLICommandBuilder(
            args=args,
            config_overrides=self._config_overrides,
            env_overrides=self._env,
        ).build_command()
        logger.debug("Running async Codex CLI command: %s", command.argv)
        runner = AsyncCodexProcessRunner(executable_path=self._executable_path)
        async for line in runner.stream_lines(command):
            yield line
        logger.debug("Finished async Codex CLI command: %s", command.argv)
