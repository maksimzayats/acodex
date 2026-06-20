from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from acodex.cli.codex import CodexAppError, CodexAppManager
from acodex.cli.doctor import Doctor
from acodex.cli.server import ServerError, ServerManager
from acodex.config import ConfigError, get_config_path, init_config, load_config

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
codex_app = typer.Typer(no_args_is_help=True)
server_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(codex_app, name="codex")
app.add_typer(server_app, name="server")


@app.command()
def doctor(
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
    deep: Annotated[bool, typer.Option("--deep", help="Run deeper MCP probes.")] = False,
) -> None:
    result = Doctor().run(deep=deep)
    if json_output:
        _echo_json(result)
    else:
        for check in result["checks"]:
            typer.echo(f"{check['status'].upper()} {check['name']}: {check['detail']}")
    if not result["ok"]:
        raise typer.Exit(1)


@config_app.command("path")
def config_path() -> None:
    typer.echo(str(get_config_path()))


@config_app.command("show")
def config_show() -> None:
    try:
        _echo_json(load_config().model_dump(mode="json"))
    except ConfigError as exc:
        _fail(str(exc))


@config_app.command("init")
def config_init() -> None:
    path = init_config()
    typer.echo(str(path))


@codex_app.command("status")
def codex_status() -> None:
    try:
        status = CodexAppManager().status(load_config())
    except ConfigError as exc:
        _fail(str(exc))
    for key, value in status.items():
        typer.echo(f"{key}: {value}")


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
    try:
        typer.echo(_relaunch_codex(app_path=app_path, port=port, yes=yes))
    except (ConfigError, CodexAppError) as exc:
        _fail(str(exc))


@server_app.command("start")
def server_start(
    host: Annotated[str | None, typer.Option("--host", help="HTTP bind host.")] = None,
    port: Annotated[int | None, typer.Option("--port", help="HTTP bind port.")] = None,
) -> None:
    try:
        config = load_config(server_host=host, server_port=port)
        state = ServerManager().start(config)
    except (ConfigError, ServerError) as exc:
        _fail(str(exc))
    typer.echo(f"HTTP: {state.base_url}")
    typer.echo(f"MCP: {state.mcp_url}")


@server_app.command("stop")
def server_stop(
    *,
    force: Annotated[bool, typer.Option("--force", help="Escalate to SIGKILL if needed.")] = False,
) -> None:
    try:
        stopped = ServerManager().stop(force=force)
    except ServerError as exc:
        _fail(str(exc))
    typer.echo("Stopped managed server" if stopped else "Managed server is not running")


@server_app.command("status")
def server_status(
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    status = ServerManager().status()
    if json_output:
        _echo_json(status)
        return
    if status["running"]:
        health = "healthy" if status["healthy"] else "unreachable"
        typer.echo(f"Running at {status['base_url']} ({health})")
    else:
        typer.echo("Managed server is not running")


@server_app.command("logs")
def server_logs(
    tail: Annotated[int, typer.Option("--tail", min=1, help="Number of log lines to show.")] = 50,
) -> None:
    log_path, lines = ServerManager().tail_logs(tail=tail)
    if not lines:
        typer.echo(f"No log file found at {log_path}")
        return
    for line in lines:
        typer.echo(line)


def main() -> None:
    app()


def _relaunch_codex(*, app_path: Path | None, port: int | None, yes: bool) -> str:
    config = load_config(
        codex_app_path=str(app_path) if app_path is not None else None,
        cdp_port=port,
    )
    manager = CodexAppManager()
    status = manager.status(config)
    confirmed = yes
    if status["running"] and status["detected_cdp_port"] != config.codex.cdp_port and not yes:
        confirmed = typer.confirm(
            "Codex is running without the configured CDP port. Quit and relaunch it?",
        )
    return manager.relaunch(config, confirmed=confirmed)


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2))


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
