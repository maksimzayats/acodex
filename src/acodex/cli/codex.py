from __future__ import annotations

import re
import subprocess  # noqa: S404
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error as url_error, request as url_request

from acodex.config import AcodexConfig

_PORT_RE = re.compile(r"--remote-debugging-port(?:=|\s+)(\d+)")
HTTP_OK = 200
HTTP_REDIRECT = 300


class CodexAppError(RuntimeError):
    """Raised when Codex app status or launch control fails."""


@dataclass(frozen=True, kw_only=True, slots=True)
class ProcessInfo:
    pid: int
    command: str


class CodexSystemOps:
    __slots__ = ()

    def list_processes(self) -> list[ProcessInfo]:
        """Return local process ids and command lines.

        Returns:
            Local processes visible through ps.

        """
        result = subprocess.run(
            ["/bin/ps", "axww", "-o", "pid=", "-o", "command="],
            check=True,
            capture_output=True,
            text=True,
        )
        processes: list[ProcessInfo] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            pid_text, _, command = stripped.partition(" ")
            if pid_text.isdigit() and command:
                processes.append(ProcessInfo(pid=int(pid_text), command=command))
        return processes

    def app_exists(self, app_path: str) -> bool:
        """Return whether the configured Codex app bundle exists.

        Returns:
            True when the path exists.

        """
        return Path(app_path).exists()

    def quit_app(self) -> None:
        """Ask macOS to quit the Codex app."""
        subprocess.run(
            ["/usr/bin/osascript", "-e", 'tell application "Codex" to quit'],
            check=True,
            capture_output=True,
            text=True,
        )

    def launch_app(self, app_path: str, *, port: int) -> None:
        """Launch Codex with a remote debugging port."""
        subprocess.run(  # noqa: S603 - fixed open executable; app path is explicit user config.
            [
                "/usr/bin/open",
                app_path,
                "--args",
                f"--remote-debugging-port={port}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )


class CDPProbe:
    __slots__ = ()

    def reachable(self, base_url: str, *, timeout: float) -> bool:
        """Return whether the CDP target list is reachable.

        Returns:
            True when /json/list responds successfully.

        """
        try:
            with url_request.urlopen("{}/json/list".format(base_url), timeout=timeout) as response:  # noqa: S310
                return HTTP_OK <= response.status < HTTP_REDIRECT
        except (OSError, url_error.URLError):
            return False


@dataclass(kw_only=True, slots=True)
class CodexAppManager:
    system_ops: CodexSystemOps = field(default_factory=CodexSystemOps)
    cdp_probe: CDPProbe = field(default_factory=CDPProbe)
    poll_interval: float = 0.2

    def status(self, config: AcodexConfig) -> dict[str, Any]:
        """Return Codex app, process, and CDP status.

        Returns:
            JSON-compatible status fields.

        """
        process = self.find_codex_process(config.codex.app_path)
        detected_port = None
        process_pid = None
        if process is not None:
            detected_port = detect_cdp_port(process.command)
            process_pid = process.pid
        return {
            "app_path": config.codex.app_path,
            "app_exists": self.system_ops.app_exists(config.codex.app_path),
            "running": process is not None,
            "pid": process_pid,
            "detected_cdp_port": detected_port,
            "configured_cdp_url": config.codex.cdp_url,
            "cdp_reachable": self.cdp_probe.reachable(
                config.codex.cdp_url,
                timeout=config.codex.request_timeout,
            ),
        }

    def relaunch(self, config: AcodexConfig, *, confirmed: bool) -> str:
        """Launch or relaunch Codex with the configured CDP port.

        Returns:
            Human-readable launch outcome.

        Raises:
            CodexAppError: If confirmation is required or CDP does not become reachable.

        """
        process = self.find_codex_process(config.codex.app_path)
        if process is not None and detect_cdp_port(process.command) == config.codex.cdp_port:
            return "Codex is already running with CDP port {}".format(config.codex.cdp_port)
        if not self.system_ops.app_exists(config.codex.app_path):
            raise CodexAppError(
                "Codex app bundle does not exist: {}".format(config.codex.app_path),
            )
        if process is not None and not confirmed:
            raise CodexAppError("Codex is running without the configured CDP port")
        if process is not None:
            self._quit_running_app()
            self._wait_until_stopped(config.codex.app_path, timeout=config.codex.launch_timeout)
        self._launch_app(config)
        if not self.wait_for_cdp(config):
            raise CodexAppError(
                "Codex CDP did not become reachable at {}".format(config.codex.cdp_url)
            )
        return "Codex launched with CDP port {}".format(config.codex.cdp_port)

    def wait_for_cdp(self, config: AcodexConfig) -> bool:
        """Wait until the configured CDP endpoint responds.

        Returns:
            True when the CDP endpoint becomes reachable before timeout.

        """
        deadline = time.monotonic() + config.codex.launch_timeout
        while time.monotonic() < deadline:
            if self.cdp_probe.reachable(config.codex.cdp_url, timeout=config.codex.request_timeout):
                return True
            time.sleep(self.poll_interval)
        return False

    def find_codex_process(self, app_path: str) -> ProcessInfo | None:
        """Return the first process that appears to be Codex.

        Returns:
            Matching process information, if found.

        """
        executable_paths = _codex_executable_paths(app_path)
        for process in self.system_ops.list_processes():
            if _is_codex_app_process(process.command, executable_paths):
                return process
        return None

    def _wait_until_stopped(self, app_path: str, *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.find_codex_process(app_path) is None:
                return
            time.sleep(self.poll_interval)

    def _quit_running_app(self) -> None:
        try:
            self.system_ops.quit_app()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CodexAppError("Unable to quit Codex before relaunch") from exc

    def _launch_app(self, config: AcodexConfig) -> None:
        try:
            self.system_ops.launch_app(config.codex.app_path, port=config.codex.cdp_port)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CodexAppError(
                "Unable to launch Codex from {}".format(config.codex.app_path),
            ) from exc


def detect_cdp_port(command: str) -> int | None:
    match = _PORT_RE.search(command)
    if match is None:
        return None
    return int(match.group(1))


def _codex_executable_paths(app_path: str) -> tuple[str, ...]:
    app = Path(app_path)
    executable_names = [app.stem]
    if app.stem != "Codex":
        executable_names.append("Codex")
    return tuple(str(app / "Contents" / "MacOS" / executable) for executable in executable_names)


def _is_codex_app_process(command: str, executable_paths: tuple[str, ...]) -> bool:
    return any(
        command == executable or command.startswith(f"{executable} ")
        for executable in executable_paths
    )
