from __future__ import annotations

from typing import Annotated

import typer

from acodex.cli.commands.services import ServerCommandService

server_app = typer.Typer(no_args_is_help=True)


@server_app.command("start")
def server_start(
    host: Annotated[str | None, typer.Option("--host", help="HTTP bind host.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="HTTP bind port.")] = None,
) -> None:
    ServerCommandService().start(host=host, port=port)


@server_app.command("stop")
def server_stop(
    *,
    force: Annotated[bool, typer.Option("--force", help="Escalate to SIGKILL if needed.")] = False,
) -> None:
    ServerCommandService().stop(force=force)


@server_app.command("status")
def server_status(
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    ServerCommandService().status(json_output=json_output)


@server_app.command("logs")
def server_logs(
    tail: Annotated[int, typer.Option("--tail", min=1, help="Number of log lines to show.")] = 50,
) -> None:
    ServerCommandService().logs(tail=tail)
