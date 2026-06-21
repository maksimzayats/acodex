from __future__ import annotations

from typing import Annotated

import typer

from acodex.cli.commands.services import DoctorCommandService

root_app = typer.Typer(no_args_is_help=True)


@root_app.command()
def doctor(
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
    deep: Annotated[bool, typer.Option("--deep", help="Run deeper MCP probes.")] = False,
) -> None:
    DoctorCommandService().run(json_output=json_output, deep=deep)
