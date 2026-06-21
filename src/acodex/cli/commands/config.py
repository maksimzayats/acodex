from __future__ import annotations

import typer

from acodex.cli.commands.services import ConfigCommandService

config_app = typer.Typer(no_args_is_help=True)


@config_app.command("path")
def config_path() -> None:
    ConfigCommandService().path()


@config_app.command("show")
def config_show() -> None:
    ConfigCommandService().show()


@config_app.command("init")
def config_init() -> None:
    ConfigCommandService().init()
