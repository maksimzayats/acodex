from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, NoReturn, TypeAlias

import typer
from rich import box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DisplayRows: TypeAlias = list[tuple[str, object]]

STYLE_SUCCESS = "bold green"
STYLE_ERROR = "bold red"
STYLE_WARNING = "bold yellow"
STYLE_MUTED = "dim"
STYLE_CYAN = "cyan"


@dataclass(kw_only=True, slots=True)
class CliPresenter:
    """Shared Rich output helpers for CLI commands."""

    console: Console = field(default_factory=Console)
    error_console: Console = field(default_factory=lambda: Console(stderr=True))

    def json(self, json_payload: Any) -> None:
        """Print a JSON payload."""
        self.console.print_json(json.dumps(json_payload, indent=2))

    def fail(self, message: str) -> NoReturn:
        """Print an error and exit the CLI."""
        self.error_console.print(Text.assemble(("Error: ", STYLE_ERROR), (message, "red")))
        raise typer.Exit(1)

    def key_values(self, title: str, rows: DisplayRows) -> None:
        """Print a two-column key/value panel."""
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(style="bold", no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        for row_label, row_payload in rows:
            table.add_row(row_label, self.render_value(row_payload))
        self.console.print(self.panel(title, table))

    def success(self, message: str, detail: str | None = None) -> None:
        """Print a success message."""
        self._print_text(message, style=STYLE_SUCCESS, detail=detail)

    def warning(self, message: str, detail: str | None = None) -> None:
        """Print a warning message."""
        self._print_text(message, style=STYLE_WARNING, detail=detail)

    def yes_no(self, *, enabled: bool) -> Text:
        """Return a styled yes/no value."""
        if enabled:
            return Text("Yes", style=STYLE_SUCCESS)
        return Text("No", style=STYLE_ERROR)

    def muted(self, message: str) -> Text:
        """Return dimmed text."""
        return Text(message, style=STYLE_MUTED)

    def panel(self, title: str, renderable: RenderableType) -> Panel:
        """Return the project panel style."""
        return Panel(
            renderable,
            title=title,
            title_align="left",
            box=box.ROUNDED,
            border_style=STYLE_MUTED,
            padding=(0, 1),
        )

    def render_value(self, row_payload: object) -> str | Text:
        """Return a table-safe rendered value."""
        if isinstance(row_payload, Text):
            return row_payload
        if row_payload is None:
            return self.muted("Not available")
        return str(row_payload)

    def _print_text(self, message: str, *, style: str, detail: str | None) -> None:
        rendered_text = Text(message, style=style)
        if detail is not None:
            rendered_text.append(f"\n{detail}", style=STYLE_CYAN)
        self.console.print(rendered_text)
