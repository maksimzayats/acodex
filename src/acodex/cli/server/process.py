from __future__ import annotations

import os
import signal
import subprocess  # noqa: S404
from typing import BinaryIO


class ProcessOps:
    """Operate on managed server processes."""

    __slots__ = ()

    def is_running(self, pid: int) -> bool:
        """Return whether a process id appears to still be alive."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def is_expected_process(self, pid: int, expected_command: list[str]) -> bool:
        """Return whether a process is live and matches managed state."""
        if not self.is_running(pid):
            return False
        return self.matches_command(pid, expected_command)

    def matches_command(self, pid: int, expected_command: list[str]) -> bool:
        """Return whether a live process command matches managed server state."""
        if not expected_command:
            return False
        command_line = self.command_line(pid)
        if command_line is None:
            return False
        return command_line == " ".join(expected_command)

    def command_line(self, pid: int) -> str | None:
        """Read the process command line for identity checks."""
        if not self.is_running(pid):
            return None
        try:
            result = subprocess.run(  # noqa: S603 - fixed ps executable; pid is converted to text.
                ["/bin/ps", "-p", str(pid), "-o", "command="],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        command = result.stdout.strip()
        if not command:
            return None
        return command

    def spawn(self, command: list[str], log_file: BinaryIO) -> int:
        """Spawn the managed server as a detached child process."""
        process = subprocess.Popen(  # noqa: S603 - command is local executable/options.
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return process.pid

    def terminate(self, pid: int) -> None:
        """Send SIGTERM to the managed process."""
        os.kill(pid, signal.SIGTERM)

    def kill(self, pid: int) -> None:
        """Send SIGKILL to the managed process."""
        os.kill(pid, signal.SIGKILL)
