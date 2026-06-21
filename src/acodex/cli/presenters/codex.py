from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rich.text import Text

from acodex.cli.presenters.base import CliPresenter, DisplayRows


@dataclass(kw_only=True, slots=True)
class CodexPresenter:
    """Render Codex app command output."""

    base: CliPresenter = field(default_factory=CliPresenter)

    def status(self, codex_status: dict[str, Any]) -> None:
        """Render Codex app status."""
        self.base.key_values("Codex App Status", self._status_rows(codex_status))
        self._print_status_warning(codex_status)

    def _status_rows(self, codex_status: dict[str, Any]) -> DisplayRows:
        detected_port = codex_status.get("detected_cdp_port")
        detected_port_text: object = self.base.muted("Not detected")
        if detected_port is not None:
            detected_port_text = detected_port
        return [
            ("App path", codex_status["app_path"]),
            ("App installed", self.base.yes_no(enabled=bool(codex_status["app_exists"]))),
            ("Process", self._process_text(codex_status)),
            ("Detected CDP port", detected_port_text),
            ("Configured CDP URL", codex_status["configured_cdp_url"]),
            ("CDP reachable", self.base.yes_no(enabled=bool(codex_status["cdp_reachable"]))),
        ]

    def _process_text(self, codex_status: dict[str, Any]) -> Text:
        running = bool(codex_status["running"])
        process_text = (
            Text("Running", style="bold green") if running else Text("Not running", style="yellow")
        )
        process_pid = codex_status.get("pid")
        if running and process_pid is not None:
            process_text.append(f" (PID {process_pid})", style="dim")
        return process_text

    def _print_status_warning(self, codex_status: dict[str, Any]) -> None:
        if not codex_status["app_exists"]:
            self.base.warning("Codex.app was not found at the configured path")
        elif not codex_status["running"]:
            self.base.warning("Codex is not running")
        elif not codex_status["cdp_reachable"]:
            self.base.warning("CDP is not reachable; relaunch Codex with the configured port")
