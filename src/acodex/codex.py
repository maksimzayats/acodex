from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from acodex.exec import AsyncCodexExec, CodexExec
from acodex.thread import AsyncThread, Thread
from acodex.types.codex_options import CodexOptions
from acodex.types.thread_options import ThreadOptions

if TYPE_CHECKING:
    from typing_extensions import Unpack


logger = logging.getLogger(__name__)


class Codex:
    """Codex is the main class for interacting with the Codex agent.

    Use `start_thread()` to start a new thread or `resume_thread()` to resume a previously started
    thread.
    """

    def __init__(self, **options: Unpack[CodexOptions]) -> None:
        self._options = options
        self._exec = CodexExec(
            executable_path=self._options.get("codex_path_override"),
            env=self._options.get("env"),
            config_overrides=self._options.get("config"),
        )
        logger.info(
            "Initialized Codex client (path_override=%s, env_overrides=%s, config_overrides=%s)",
            self._options.get("codex_path_override") is not None,
            self._options.get("env") is not None,
            self._options.get("config") is not None,
        )

    def start_thread(self, **thread_options: Unpack[ThreadOptions]) -> Thread:
        """Start a new conversation with an agent.

        Returns:
            A new thread instance.

        """
        logger.info("Starting new thread")
        logger.debug("Thread options for start_thread: %s", sorted(thread_options))
        return Thread(
            exec=self._exec,
            options=self._options,
            thread_options=thread_options,
        )

    def resume_thread(self, thread_id: str, **thread_options: Unpack[ThreadOptions]) -> Thread:
        """Resume a conversation with an agent using a thread ID.

        Threads are persisted in ``~/.codex/sessions``.

        Args:
            thread_id: Identifier of the thread to resume.

        Returns:
            A new thread instance.

        """
        logger.info("Resuming thread: %s", thread_id)
        logger.debug("Thread options for resume_thread: %s", sorted(thread_options))
        return Thread(
            exec=self._exec,
            options=self._options,
            thread_options=thread_options,
            thread_id=thread_id,
        )


class AsyncCodex:
    """Codex is the main class for interacting with the Codex agent.

    Use `start_thread()` to start a new thread or `resume_thread()` to resume a previously started
    thread.
    """

    def __init__(self, **options: Unpack[CodexOptions]) -> None:
        self._options = options
        self._exec = AsyncCodexExec(
            executable_path=self._options.get("codex_path_override"),
            env=self._options.get("env"),
            config_overrides=self._options.get("config"),
        )
        logger.info(
            "Initialized AsyncCodex client (path_override=%s, env_overrides=%s, config_overrides=%s)",
            self._options.get("codex_path_override") is not None,
            self._options.get("env") is not None,
            self._options.get("config") is not None,
        )

    def start_thread(self, **thread_options: Unpack[ThreadOptions]) -> AsyncThread:
        """Start a new conversation with an agent.

        Returns:
            A new thread instance.

        """
        logger.info("Starting new async thread")
        logger.debug("Thread options for async start_thread: %s", sorted(thread_options))
        return AsyncThread(
            exec=self._exec,
            options=self._options,
            thread_options=thread_options,
        )

    def resume_thread(self, thread_id: str, **options: Unpack[ThreadOptions]) -> AsyncThread:
        """Resume a conversation with an agent using a thread ID.

        Threads are persisted in ``~/.codex/sessions``.

        Args:
            thread_id: Identifier of the thread to resume.

        Returns:
            A new thread instance.

        """
        logger.info("Resuming async thread: %s", thread_id)
        logger.debug("Thread options for async resume_thread: %s", sorted(options))
        return AsyncThread(
            exec=self._exec,
            options=self._options,
            thread_options=options,
            thread_id=thread_id,
        )
