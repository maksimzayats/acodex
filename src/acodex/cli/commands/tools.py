from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from diwire import Injected, Scope, resolver_context

from acodex.cli.commands.runtime import runtime_typer_signature
from acodex.cli.presenters.base import CliPresenter
from acodex.cli.server import ServerError
from acodex.cli.tools import ToolArgumentsError, ToolOutput, ToolsCommand
from acodex.core.mcp_tools import MCPToolClientError

tools_app = typer.Typer(no_args_is_help=True)


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
        CliPresenter().fail(str(exc))


runtime_typer_signature(tools_list)


@tools_app.command(
    "call",
    context_settings={
        "allow_extra_args": True,
        "allow_interspersed_args": False,
        "ignore_unknown_options": True,
    },
)
@resolver_context.inject(scope=Scope.REQUEST)
def tools_call(
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
        CliPresenter().fail(str(exc))

    if exit_code:
        raise typer.Exit(exit_code)


runtime_typer_signature(tools_call)
