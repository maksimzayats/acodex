from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from acodex.cli.commands.services import CodexCommandService

codex_app = typer.Typer(no_args_is_help=True)


@codex_app.command("status")
def codex_status() -> None:
    CodexCommandService().status()


@codex_app.command("relaunch")
def codex_relaunch(
    *,
    yes: Annotated[bool, typer.Option("--yes", help="Do not prompt before relaunching.")] = False,
    port: Annotated[int | None, typer.Option("--port", help="CDP port to launch.")] = None,
    app_path: Annotated[
        Path | None,
        typer.Option("--app", help="Path to Codex.app."),
    ] = None,
) -> None:
    CodexCommandService().relaunch(app_path=app_path, port=port, yes=yes)
