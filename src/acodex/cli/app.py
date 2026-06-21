from __future__ import annotations

from acodex.cli.commands.codex import codex_app
from acodex.cli.commands.config import config_app
from acodex.cli.commands.root import root_app
from acodex.cli.commands.server import server_app
from acodex.cli.commands.tools import tools_app

app = root_app
app.add_typer(config_app, name="config")
app.add_typer(codex_app, name="codex")
app.add_typer(server_app, name="server")
app.add_typer(tools_app, name="tools")
