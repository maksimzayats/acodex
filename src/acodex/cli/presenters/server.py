from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.text import Text

from acodex.cli.presenters.base import CliPresenter, DisplayRows


@dataclass(kw_only=True, slots=True)
class ServerPresenter:
    """Render managed-server command output."""

    base: CliPresenter = field(default_factory=CliPresenter)

    def started(self, *, base_url: str, mcp_url: str, pid: int, log_path: str) -> None:
        """Render successful server start."""
        self.base.key_values(
            "Managed Server Started",
            [
                ("Status", Text("Running", style="bold green")),
                ("HTTP", base_url),
                ("MCP", mcp_url),
                ("PID", pid),
                ("Log file", log_path),
            ],
        )

    def status(self, server_status: dict[str, Any]) -> None:
        """Render current server status."""
        self.base.key_values("Managed Server Status", self._status_rows(server_status))

    def logs(self, log_path: Path, lines: list[str]) -> None:
        """Render server log lines or a missing-log warning."""
        if not lines:
            self.base.warning("No server log file found", str(log_path))
            return
        self.base.console.print(
            Text.assemble(("Server logs", "bold cyan"), (f"  {log_path}", "dim")),
        )
        for log_line in lines:
            self.base.console.print(log_line, highlight=False, markup=False)

    def _status_rows(self, server_status: dict[str, Any]) -> DisplayRows:
        if server_status["running"]:
            return self._running_rows(server_status)
        rows: DisplayRows = [("Status", Text("Not running", style="bold yellow"))]
        if server_status.get("state_path") is not None:
            rows.append(("State file", server_status["state_path"]))
        return rows

    def _running_rows(self, server_status: dict[str, Any]) -> DisplayRows:
        rows: DisplayRows = [
            ("Status", Text("Running", style="bold green")),
            ("Health", self._health_text(server_status)),
            ("HTTP", server_status["base_url"]),
        ]
        self._append_optional_rows(rows, server_status)
        return rows

    def _health_text(self, server_status: dict[str, Any]) -> Text:
        if server_status["healthy"]:
            return Text("Healthy", style="bold green")
        return Text("Unreachable", style="bold yellow")

    def _append_optional_rows(self, rows: DisplayRows, server_status: dict[str, Any]) -> None:
        optional_labels = (
            ("mcp_url", "MCP"),
            ("pid", "PID"),
            ("state_path", "State file"),
            ("log_path", "Log file"),
        )
        for status_key, row_label in optional_labels:
            if server_status.get(status_key) is not None:
                rows.append((row_label, server_status[status_key]))
