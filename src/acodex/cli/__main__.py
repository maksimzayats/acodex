from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, NoReturn, TypeVar, get_type_hints

import typer
from diwire import Injected, Scope, resolver_context
from rich import box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from acodex.cli.codex import CodexAppError, CodexAppManager
from acodex.cli.doctor import Doctor
from acodex.cli.server import ServerError, ServerManager
from acodex.cli.tools import ToolArgumentsError, ToolOutput, ToolsCommand
from acodex.config import ConfigError, get_config_path, init_config, load_config
from acodex.core.mcp_tools import MCPToolClientError
from acodex.ioc.container import get_cli_container

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
codex_app = typer.Typer(no_args_is_help=True)
server_app = typer.Typer(no_args_is_help=True)
tools_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(codex_app, name="codex")
app.add_typer(server_app, name="server")
app.add_typer(tools_app, name="tools")

console = Console()
error_console = Console(stderr=True)
_T = TypeVar("_T", bound=Callable[..., Any])


def _runtime_typer_signature(command: _T) -> _T:
    signature = inspect.signature(command)
    annotations = get_type_hints(command, include_extras=True)
    parameters = [
        parameter.replace(annotation=annotations.get(parameter.name, parameter.annotation))
        for parameter in signature.parameters.values()
    ]
    return_annotation = annotations.get("return", signature.return_annotation)
    command.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=parameters,
        return_annotation=return_annotation,
    )
    return command


@app.callback()
def configure_cli_dependencies() -> None:
    get_cli_container()


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
        _print_doctor_result(result)
    if not result["ok"]:
        raise typer.Exit(1)


@config_app.command("path")
def config_path() -> None:
    console.print(str(get_config_path()), style="cyan", highlight=False, soft_wrap=True)


@config_app.command("show")
def config_show() -> None:
    try:
        _echo_json(load_config().model_dump(mode="json"))
    except ConfigError as exc:
        _fail(str(exc))


@config_app.command("init")
def config_init() -> None:
    path = init_config()
    _print_key_values(
        "Configuration",
        [("Status", Text("Ready", style="bold green")), ("Path", str(path))],
    )


@codex_app.command("status")
def codex_status() -> None:
    try:
        status = CodexAppManager().status(load_config())
    except ConfigError as exc:
        _fail(str(exc))
    _print_codex_status(status)


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
        _print_success(_relaunch_codex(app_path=app_path, port=port, yes=yes))
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
    _print_key_values(
        "Managed Server Started",
        [
            ("Status", Text("Running", style="bold green")),
            ("HTTP", state.base_url),
            ("MCP", state.mcp_url),
            ("PID", state.pid),
            ("Log file", state.log_path),
        ],
    )


@server_app.command("stop")
def server_stop(
    *,
    force: Annotated[bool, typer.Option("--force", help="Escalate to SIGKILL if needed.")] = False,
) -> None:
    try:
        stopped = ServerManager().stop(force=force)
    except ServerError as exc:
        _fail(str(exc))
    if stopped:
        _print_success("Stopped managed server")
    else:
        _print_warning("Managed server is not running")


@server_app.command("status")
def server_status(
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
) -> None:
    status = ServerManager().status()
    if json_output:
        _echo_json(status)
        return
    _print_server_status(status)


@server_app.command("logs")
def server_logs(
    tail: Annotated[int, typer.Option("--tail", min=1, help="Number of log lines to show.")] = 50,
) -> None:
    log_path, lines = ServerManager().tail_logs(tail=tail)
    if not lines:
        _print_warning("No server log file found", str(log_path))
        return
    console.print(Text.assemble(("Server logs", "bold cyan"), (f"  {log_path}", "dim")))
    for line in lines:
        console.print(line, highlight=False, markup=False)


@tools_app.command("list")
@resolver_context.inject(scope=Scope.REQUEST)
def tools_list(
    *,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON output.")] = False,
    command: Injected[ToolsCommand],
) -> None:
    try:
        command.list_tools(json_output=json_output)
    except (MCPToolClientError, ServerError) as exc:
        _fail(str(exc))


_runtime_typer_signature(tools_list)


@tools_app.command(
    "call",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
        "ignore_unknown_options": True,
    },
)
@resolver_context.inject(scope=Scope.REQUEST)
def tools_call(  # noqa: PLR0913 - Typer command signatures mirror the CLI surface.
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="MCP tool name to call.")],
    *,
    output: Annotated[
        ToolOutput,
        typer.Option("--output", help="Output format for the tool result.", case_sensitive=False),
    ] = ToolOutput.text,
    args_json: Annotated[
        str | None,
        typer.Option("--args-json", help="Full tool arguments object as JSON."),
    ] = None,
    args_json_file: Annotated[
        Path | None,
        typer.Option("--args-json-file", help="Path to a JSON object with tool arguments."),
    ] = None,
    command: Injected[ToolsCommand],
) -> None:
    try:
        exit_code = command.call(
            name=name,
            raw_args=list(ctx.args),
            output=output,
            args_json=args_json,
            args_json_file=args_json_file,
        )
    except (MCPToolClientError, ServerError, ToolArgumentsError, ValueError) as exc:
        _fail(str(exc))

    if exit_code:
        raise typer.Exit(exit_code)


_runtime_typer_signature(tools_call)


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
    console.print_json(json.dumps(payload, indent=2))


def _fail(message: str) -> NoReturn:
    error_console.print(Text.assemble(("Error: ", "bold red"), (message, "red")))
    raise typer.Exit(1)


def _print_doctor_result(result: dict[str, Any]) -> None:
    checks = result["checks"]
    grid = Table.grid(
        expand=True,
        padding=(0, 2),
    )
    grid.add_column(no_wrap=True)
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    for check in checks:
        status = str(check["status"])
        grid.add_row(
            Text(_status_label(status), style=_status_style(status)),
            str(check["name"]),
            str(check["detail"]),
        )

    console.print(_panel("acodex doctor", grid))
    fixes = _doctor_fixes(checks)
    if fixes:
        console.print(_panel("Suggested fixes", _doctor_fix_table(fixes)))
    console.print(_doctor_summary(checks))


def _print_codex_status(status: dict[str, Any]) -> None:
    running = bool(status["running"])
    pid = status.get("pid")
    process = (
        Text("Running", style="bold green") if running else Text("Not running", style="yellow")
    )
    if running and pid is not None:
        process.append(f" (PID {pid})", style="dim")

    detected_port = status.get("detected_cdp_port")
    rows: list[tuple[str, object]] = [
        ("App path", status["app_path"]),
        ("App installed", _yes_no(value=bool(status["app_exists"]))),
        ("Process", process),
        (
            "Detected CDP port",
            detected_port if detected_port is not None else _muted("Not detected"),
        ),
        ("Configured CDP URL", status["configured_cdp_url"]),
        ("CDP reachable", _yes_no(value=bool(status["cdp_reachable"]))),
    ]
    _print_key_values("Codex App Status", rows)

    if not status["app_exists"]:
        _print_warning("Codex.app was not found at the configured path")
    elif not running:
        _print_warning("Codex is not running")
    elif not status["cdp_reachable"]:
        _print_warning("CDP is not reachable; relaunch Codex with the configured port")


def _print_server_status(status: dict[str, Any]) -> None:
    if status["running"]:
        rows: list[tuple[str, object]] = [
            ("Status", Text("Running", style="bold green")),
            (
                "Health",
                Text("Healthy", style="bold green")
                if status["healthy"]
                else Text("Unreachable", style="bold yellow"),
            ),
            ("HTTP", status["base_url"]),
        ]
        if status.get("mcp_url") is not None:
            rows.append(("MCP", status["mcp_url"]))
        if status.get("pid") is not None:
            rows.append(("PID", status["pid"]))
        if status.get("state_path") is not None:
            rows.append(("State file", status["state_path"]))
        if status.get("log_path") is not None:
            rows.append(("Log file", status["log_path"]))
        _print_key_values("Managed Server Status", rows)
        return

    rows = [("Status", Text("Not running", style="bold yellow"))]
    if status.get("state_path") is not None:
        rows.append(("State file", status["state_path"]))
    _print_key_values("Managed Server Status", rows)


def _print_key_values(
    title: str,
    rows: list[tuple[str, object]],
) -> None:
    grid = Table.grid(
        expand=True,
        padding=(0, 2),
    )
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    for label, value in rows:
        grid.add_row(label, _render_value(value))
    console.print(_panel(title, grid))


def _print_success(message: str, detail: str | None = None) -> None:
    text = Text(message, style="bold green")
    if detail is not None:
        text.append(f"\n{detail}", style="cyan")
    console.print(text)


def _print_warning(message: str, detail: str | None = None) -> None:
    text = Text(message, style="bold yellow")
    if detail is not None:
        text.append(f"\n{detail}", style="cyan")
    console.print(text)


def _render_value(value: object) -> str | Text:
    if isinstance(value, Text):
        return value
    return _muted("Not available") if value is None else str(value)


def _yes_no(*, value: bool) -> Text:
    return Text("Yes", style="bold green") if value else Text("No", style="bold red")


def _muted(value: str) -> Text:
    return Text(value, style="dim")


def _panel(title: str, renderable: RenderableType) -> Panel:
    return Panel(
        renderable,
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style="dim",
        padding=(0, 1),
    )


def _status_label(status: str) -> str:
    return {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}.get(status, status.upper())


def _status_style(status: str) -> str:
    return {"pass": "bold green", "warn": "bold yellow", "fail": "bold red"}.get(
        status,
        "bold white",
    )


def _doctor_summary(checks: list[dict[str, Any]]) -> Text:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        status = str(check["status"])
        if status in counts:
            counts[status] += 1

    if counts["fail"]:
        return Text(
            f"{_plural(counts['fail'], 'failing check')} found; fix failures before continuing.",
            style="bold red",
        )
    if counts["warn"]:
        return Text(
            f"No failing checks; {_plural(counts['warn'], 'warning')} need attention.",
            style="bold yellow",
        )
    return Text(f"All {_plural(counts['pass'], 'check')} passed.", style="bold green")


def _plural(count: int, noun: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count} {noun}{suffix}"


def _doctor_fixes(checks: list[dict[str, Any]]) -> list[tuple[str, dict[str, str]]]:
    fixes: list[tuple[str, dict[str, str]]] = []
    seen: set[tuple[str, str, str]] = set()
    for check in checks:
        if check.get("status") == "pass":
            continue
        raw_fix = check.get("fix")
        if not isinstance(raw_fix, dict):
            continue

        summary = str(raw_fix.get("summary", "")).strip()
        command = str(raw_fix.get("command", "")).strip()
        detail = str(raw_fix.get("detail", "")).strip()
        if not summary and not command:
            continue

        key = (summary, command, detail)
        if key in seen:
            continue
        seen.add(key)

        fix: dict[str, str] = {"summary": summary}
        if command:
            fix["command"] = command
        if detail:
            fix["detail"] = detail
        fixes.append((str(check.get("name", "check")), fix))
    return fixes


def _doctor_fix_table(fixes: list[tuple[str, dict[str, str]]]) -> Table:
    table = Table.grid(expand=True, padding=(0, 2))
    table.add_column(no_wrap=True, style="bold cyan")
    table.add_column(ratio=1, overflow="fold")

    for index, (check_name, fix) in enumerate(fixes, start=1):
        label = Text(f"{index}. {check_name}", style="bold cyan")
        detail = Text(fix["summary"], style="bold white")
        if fix.get("detail"):
            detail.append("\n")
            detail.append(fix["detail"], style="dim")
        if fix.get("command"):
            detail.append("\n$ ", style="dim")
            detail.append(fix["command"], style="bold cyan")
        table.add_row(label, detail)
    return table


if __name__ == "__main__":  # pragma: no cover
    main()
