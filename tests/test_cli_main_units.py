from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

from acodex.cli import __main__ as cli, tools as cli_tools
from acodex.cli.codex import CodexAppError
from acodex.cli.commands import (
    codex as codex_commands,
    root as root_commands,
    server as server_commands,
    services as command_services,
)
from acodex.cli.presenters.base import CliPresenter
from acodex.cli.presenters.codex import CodexPresenter
from acodex.cli.presenters.doctor import DoctorPresenter
from acodex.cli.presenters.server import ServerPresenter
from acodex.cli.server import ServerError, ServerState
from acodex.config import AcodexConfig
from acodex.ioc import container as container_module

runner = CliRunner()


def capture_console() -> tuple[StringIO, CliPresenter]:
    output = StringIO()
    presenter = CliPresenter(
        console=Console(file=output, force_terminal=False, color_system=None, width=100),
        error_console=Console(
            file=StringIO(),
            force_terminal=False,
            color_system=None,
            width=100,
        ),
    )
    return output, presenter


class FakeDoctor:
    def __init__(self) -> None:
        self.called = True

    def run(self, *, deep: bool) -> dict[str, Any]:
        return {
            "ok": not deep,
            "checks": [{"name": "config", "status": "fail" if deep else "pass", "detail": "x"}],
        }


class FakeDoctorWithFix:
    def run(self, *, deep: bool) -> dict[str, Any]:
        return {
            "ok": True,
            "checks": [
                {
                    "name": "server",
                    "status": "warn",
                    "detail": "http://127.0.0.1:45218",
                    "fix": {
                        "summary": "Start the managed acodex HTTP server.",
                        "command": "acodex server start",
                    },
                },
            ],
        }


class FakeCodexManager:
    def __init__(self) -> None:
        self.relaunch_confirmed: bool | None = None

    def status(self, config: AcodexConfig) -> dict[str, Any]:
        return {
            "app_path": config.codex.app_path,
            "app_exists": True,
            "running": True,
            "pid": 1,
            "detected_cdp_port": None,
            "configured_cdp_url": config.codex.cdp_url,
            "cdp_reachable": False,
        }

    def relaunch(self, config: AcodexConfig, *, confirmed: bool) -> str:
        self.relaunch_confirmed = confirmed
        if not confirmed:
            raise CodexAppError("no confirmation")
        return f"relaunched {config.codex.cdp_port}"


class FakeServerManager:
    def __init__(self) -> None:
        self.force = False

    def start(self, config: AcodexConfig) -> ServerState:
        if config.server.host == "fail":
            raise ServerError("start failed")
        return ServerState(
            pid=1,
            host=config.server.host,
            port=config.server.port,
            base_url=f"http://{config.server.host}:{config.server.port}",
            mcp_url=f"http://{config.server.host}:{config.server.port}/mcp",
            started_at=1.0,
            log_path="server.log",
            command=["uvicorn"],
        )

    def stop(self, *, force: bool) -> bool:
        self.force = force
        return force

    def status(self) -> dict[str, Any]:
        return {"running": True, "healthy": False, "base_url": "http://127.0.0.1:45218"}

    def tail_logs(self, *, tail: int) -> tuple[Path, list[str]]:
        if tail == 1:
            return Path("server.log"), ["last"]
        return Path("server.log"), []


class FakeToolsClient:
    calls: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    urls: ClassVar[list[str]] = []
    tools: ClassVar[list[dict[str, Any]]] = [
        {
            "name": "codex_app.list_threads",
            "description": "List Codex threads.",
        },
    ]
    result: ClassVar[dict[str, Any]] = {
        "content": [{"type": "text", "text": "ok"}],
        "isError": False,
    }

    def __init__(self, *, mcp_url: str) -> None:
        self.urls.append(mcp_url)

    def list_tools(self) -> list[dict[str, Any]]:
        return self.tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return self.result


def test_help_and_config_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setenv("ACODEX_CONFIG", str(path))

    assert runner.invoke(cli.app, ["--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["config", "path"]).stdout.strip() == str(path)

    init = runner.invoke(cli.app, ["config", "init"])
    assert init.exit_code == 0
    assert path.exists()

    show = runner.invoke(cli.app, ["config", "show"])
    assert show.exit_code == 0
    assert json.loads(show.stdout)["server"]["port"] == 45218


def test_config_show_invalid_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("ACODEX_CONFIG", str(path))

    result = runner.invoke(cli.app, ["config", "show"])

    assert result.exit_code == 1
    assert "Invalid JSON" in result.stderr


def test_doctor_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        root_commands,
        "DoctorCommandService",
        lambda: command_services.DoctorCommandService(doctor=cast("Any", FakeDoctor())),
    )

    human = runner.invoke(cli.app, ["doctor"])
    assert human.exit_code == 0
    assert "acodex doctor" in human.stdout
    assert "PASS" in human.stdout
    assert "config" in human.stdout
    assert "All 1 check passed" in human.stdout

    as_json = runner.invoke(cli.app, ["doctor", "--json", "--deep"])
    assert as_json.exit_code == 1
    assert json.loads(as_json.stdout)["ok"] is False


def test_doctor_outputs_suggested_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        root_commands,
        "DoctorCommandService",
        lambda: command_services.DoctorCommandService(doctor=cast("Any", FakeDoctorWithFix())),
    )

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "Suggested fixes" in result.stdout
    assert "Start the managed acodex HTTP server" in result.stdout
    assert "acodex server start" in result.stdout


def test_doctor_output_helpers_cover_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    output, presenter = capture_console()
    checks: list[dict[str, Any]] = [
        {"name": "passed", "status": "pass", "detail": "ok"},
        {"name": "unknown", "status": "mystery", "detail": "custom"},
        {"name": "bad-fix", "status": "warn", "detail": "skip", "fix": "invalid"},
        {
            "name": "empty-fix",
            "status": "warn",
            "detail": "skip",
            "fix": {"summary": " ", "command": " "},
        },
        {
            "name": "detail-only",
            "status": "warn",
            "detail": "needs detail",
            "fix": {"summary": "Read the detail", "detail": "More context"},
        },
        {
            "name": "with-command",
            "status": "warn",
            "detail": "needs command",
            "fix": {
                "summary": "Run the command",
                "detail": "Then retry.",
                "command": "acodex server start",
            },
        },
        {
            "name": "duplicate-command",
            "status": "warn",
            "detail": "same fix",
            "fix": {
                "summary": "Run the command",
                "detail": "Then retry.",
                "command": "acodex server start",
            },
        },
        {
            "name": "failure",
            "status": "fail",
            "detail": "broken",
            "fix": {"summary": "Fix the failure"},
        },
    ]

    DoctorPresenter(base=presenter).result({"ok": False, "checks": checks})

    rendered = output.getvalue()
    assert "MYSTERY" in rendered
    assert "Suggested fixes" in rendered
    assert "Read the detail" in rendered
    assert "Then retry." in rendered
    assert "Fix the failure" in rendered
    assert "1 failing check found" in rendered


def test_codex_status_and_relaunch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCodexManager()
    path = tmp_path / "config.json"
    monkeypatch.setenv("ACODEX_CONFIG", str(path))
    monkeypatch.setattr(
        codex_commands,
        "CodexCommandService",
        lambda: command_services.CodexCommandService(manager=cast("Any", fake)),
    )

    status = runner.invoke(cli.app, ["codex", "status"])
    assert status.exit_code == 0
    assert "Codex App Status" in status.stdout
    assert "Running" in status.stdout
    assert "CDP is not reachable" in status.stdout

    denied = runner.invoke(cli.app, ["codex", "relaunch"], input="n\n")
    assert denied.exit_code == 1
    assert "no confirmation" in denied.stderr

    relaunched = runner.invoke(cli.app, ["codex", "relaunch", "--yes", "--port", "6000"])
    assert relaunched.exit_code == 0
    assert "relaunched 6000" in relaunched.stdout

    relaunched_with_app = runner.invoke(
        cli.app,
        ["codex", "relaunch", "--yes", "--app", str(tmp_path / "Codex.app"), "--port", "6001"],
    )
    assert relaunched_with_app.exit_code == 0
    assert "relaunched 6001" in relaunched_with_app.stdout


def test_codex_status_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("ACODEX_CONFIG", str(path))

    result = runner.invoke(cli.app, ["codex", "status"])

    assert result.exit_code == 1
    assert "Invalid JSON" in result.stderr


def test_codex_status_warning_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    output, presenter = capture_console()
    base: dict[str, Any] = {
        "app_path": "/Applications/Codex.app",
        "detected_cdp_port": None,
        "configured_cdp_url": "http://127.0.0.1:9222",
    }

    CodexPresenter(base=presenter).status(
        base
        | {
            "app_exists": False,
            "running": False,
            "pid": None,
            "cdp_reachable": False,
        },
    )
    CodexPresenter(base=presenter).status(
        base
        | {
            "app_exists": True,
            "running": False,
            "pid": None,
            "cdp_reachable": False,
        },
    )
    CodexPresenter(base=presenter).status(
        base
        | {
            "app_exists": True,
            "running": True,
            "pid": None,
            "cdp_reachable": False,
        },
    )
    CodexPresenter(base=presenter).status(
        base
        | {
            "app_exists": True,
            "running": True,
            "pid": 123,
            "detected_cdp_port": 9222,
            "cdp_reachable": True,
        },
    )

    rendered = output.getvalue()
    assert "Codex.app was not found" in rendered
    assert "Codex is not running" in rendered
    assert "CDP is not reachable" in rendered
    assert "PID 123" in rendered


def test_server_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeServerManager()
    monkeypatch.setenv("ACODEX_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        server_commands,
        "ServerCommandService",
        lambda: command_services.ServerCommandService(manager=cast("Any", fake)),
    )

    start = runner.invoke(cli.app, ["server", "start", "--host", "127.0.0.2", "--port", "9000"])
    assert start.exit_code == 0
    assert "Managed Server Started" in start.stdout
    assert "HTTP" in start.stdout
    assert "http://127.0.0.2:9000" in start.stdout

    failed = runner.invoke(cli.app, ["server", "start", "--host", "fail"])
    assert failed.exit_code == 1
    assert "start failed" in failed.stderr

    not_stopped = runner.invoke(cli.app, ["server", "stop"])
    assert not_stopped.exit_code == 0
    assert "Managed server is not running" in not_stopped.stdout

    stopped = runner.invoke(cli.app, ["server", "stop", "--force"])
    assert stopped.exit_code == 0
    assert "Stopped" in stopped.stdout

    status = runner.invoke(cli.app, ["server", "status"])
    assert status.exit_code == 0
    assert "Unreachable" in status.stdout

    status_json = runner.invoke(cli.app, ["server", "status", "--json"])
    assert json.loads(status_json.stdout)["running"] is True

    logs = runner.invoke(cli.app, ["server", "logs", "--tail", "1"])
    assert "Server logs" in logs.stdout
    assert "last" in logs.stdout

    no_logs = runner.invoke(cli.app, ["server", "logs"])
    assert "No server log file found" in no_logs.stdout


def test_tools_list_and_call_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    class ToolsServerManager:
        def status(self) -> dict[str, Any]:
            return {
                "running": True,
                "healthy": True,
                "mcp_url": "http://127.0.0.1:45218/mcp",
            }

    FakeToolsClient.calls = []
    FakeToolsClient.urls = []
    FakeToolsClient.tools = [
        {
            "name": "codex_app.list_threads",
            "description": "List Codex threads.",
        },
    ]
    FakeToolsClient.result = {
        "content": [{"type": "text", "text": "called"}],
        "isError": False,
    }
    monkeypatch.setattr(container_module, "build_server_manager", ToolsServerManager)
    monkeypatch.setattr(
        container_module,
        "build_tools_client_factory",
        lambda: cli_tools.MCPToolsClientFactory(client_class=cast("Any", FakeToolsClient)),
    )

    listed = runner.invoke(cli.app, ["tools", "list"])
    assert listed.exit_code == 0
    assert "Codex Tools" in listed.stdout
    assert "codex_app.list_threads" in listed.stdout

    listed_json = runner.invoke(cli.app, ["tools", "list", "--json"])
    assert listed_json.exit_code == 0
    assert json.loads(listed_json.stdout)["tools"][0]["name"] == "codex_app.list_threads"

    called = runner.invoke(
        cli.app,
        [
            "tools",
            "call",
            "codex_app.list_threads",
            "--limit=1",
            "--query",
            "open issues",
            "--includeArchived",
        ],
    )
    assert called.exit_code == 0
    assert called.stdout.strip() == "called"
    assert FakeToolsClient.urls == [
        "http://127.0.0.1:45218/mcp",
        "http://127.0.0.1:45218/mcp",
        "http://127.0.0.1:45218/mcp",
    ]
    assert FakeToolsClient.calls == [
        (
            "codex_app.list_threads",
            {"limit": 1, "query": "open issues", "includeArchived": True},
        ),
    ]

    called_json = runner.invoke(
        cli.app,
        ["tools", "call", "--output", "json", "codex_app.list_threads", "--limit", "2"],
    )
    assert called_json.exit_code == 0
    assert json.loads(called_json.stdout)["content"][0]["text"] == "called"
    assert FakeToolsClient.calls[-1] == ("codex_app.list_threads", {"limit": 2})

    called_with_args_json = runner.invoke(
        cli.app,
        ["tools", "call", "--args-json", '{"payload":{"nested":true}}', "codex_app.echo"],
    )
    assert called_with_args_json.exit_code == 0
    args_json_call = cast("Any", FakeToolsClient.calls[-1])
    assert args_json_call[0] == "codex_app.echo"
    assert args_json_call[1]["payload"] == {"nested": True}

    call_with_tool_output_arg = runner.invoke(
        cli.app,
        ["tools", "call", "codex_app.echo", "--output", "json"],
    )
    assert call_with_tool_output_arg.exit_code == 0
    output_arg_call = cast("Any", FakeToolsClient.calls[-1])
    assert output_arg_call == ("codex_app.echo", {"output": "json"})


def test_tools_call_tool_help(monkeypatch: pytest.MonkeyPatch) -> None:
    class ToolsServerManager:
        def status(self) -> dict[str, Any]:
            return {
                "running": True,
                "healthy": True,
                "mcp_url": "http://127.0.0.1:45218/mcp",
            }

    FakeToolsClient.calls = []
    FakeToolsClient.tools = [
        {
            "name": "codex_app.list_threads",
            "description": "List Codex threads.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "number"}},
            },
        },
    ]
    monkeypatch.setattr(container_module, "build_server_manager", ToolsServerManager)
    monkeypatch.setattr(
        container_module,
        "build_tools_client_factory",
        lambda: cli_tools.MCPToolsClientFactory(client_class=cast("Any", FakeToolsClient)),
    )

    help_result = runner.invoke(cli.app, ["tools", "call", "codex_app.list_threads", "--help"])
    assert help_result.exit_code == 0
    assert "Tool Help" in help_result.stdout
    assert "Input schema" in help_result.stdout
    assert '"limit"' in help_result.stdout
    assert "Default output payload shape" in help_result.stdout
    assert '"schemaVersion"' in help_result.stdout
    assert '"threads"' in help_result.stdout
    assert "Raw MCP result (--output json)" in help_result.stdout
    assert FakeToolsClient.calls == []

    bare_help_result = runner.invoke(cli.app, ["tools", "call", "list_threads", "--help"])
    assert bare_help_result.exit_code == 0
    assert "codex_app.list_threads" in bare_help_result.stdout

    missing_help_result = runner.invoke(cli.app, ["tools", "call", "missing", "--help"])
    assert missing_help_result.exit_code == 1
    assert "Tool not found: missing" in missing_help_result.stderr


def test_tools_call_tool_help_handles_output_schema_and_missing_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ToolsServerManager:
        def status(self) -> dict[str, Any]:
            return {
                "running": True,
                "healthy": True,
                "mcp_url": "http://127.0.0.1:45218/mcp",
            }

    FakeToolsClient.calls = []
    FakeToolsClient.tools = [
        {
            "name": "codex_app.echo",
            "description": "Echo a value.",
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object", "properties": {"value": {"type": "string"}}},
        },
        {
            "name": "codex_app.unknown_output",
            "description": "No output schema.",
            "inputSchema": {"type": "object"},
        },
    ]
    monkeypatch.setattr(container_module, "build_server_manager", ToolsServerManager)
    monkeypatch.setattr(
        container_module,
        "build_tools_client_factory",
        lambda: cli_tools.MCPToolsClientFactory(client_class=cast("Any", FakeToolsClient)),
    )

    schema_help = runner.invoke(cli.app, ["tools", "call", "codex_app.echo", "--help"])
    assert schema_help.exit_code == 0
    assert "Default output payload shape" in schema_help.stdout
    assert '"value"' in schema_help.stdout

    missing_schema_help = runner.invoke(
        cli.app,
        ["tools", "call", "codex_app.unknown_output", "--help"],
    )
    assert missing_schema_help.exit_code == 0
    assert "This tool descriptor does not declare an output schema" in missing_schema_help.stdout


def test_tools_command_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorToolsClient(FakeToolsClient):
        result: ClassVar[dict[str, Any]] = {
            "content": [{"type": "text", "text": "tool failed"}],
            "isError": True,
        }

    class ToolsServerManager:
        def status(self) -> dict[str, Any]:
            return {
                "running": True,
                "healthy": True,
                "mcp_url": "http://127.0.0.1:45218/mcp",
            }

    monkeypatch.setattr(container_module, "build_server_manager", ToolsServerManager)
    monkeypatch.setattr(
        container_module,
        "build_tools_client_factory",
        lambda: cli_tools.MCPToolsClientFactory(client_class=cast("Any", ErrorToolsClient)),
    )

    failed_tool = runner.invoke(cli.app, ["tools", "call", "codex_app.fail"])
    assert failed_tool.exit_code == 1
    assert "tool failed" in failed_tool.stdout

    invalid_args = runner.invoke(cli.app, ["tools", "call", "codex_app.echo", "limit=1"])
    assert invalid_args.exit_code == 1
    assert "must use --name value" in invalid_args.stderr


def test_tools_list_empty_and_server_status_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def server_manager_for_status(server_status: dict[str, Any]) -> type:
        class StatusServerManager:
            def status(self) -> dict[str, Any]:
                return server_status

        return StatusServerManager

    class EmptyToolsClient(FakeToolsClient):
        tools: ClassVar[list[dict[str, Any]]] = []

    class EmptyToolsServerManager:
        def status(self) -> dict[str, Any]:
            return {
                "running": True,
                "healthy": True,
                "mcp_url": "http://127.0.0.1:45218/mcp",
            }

    monkeypatch.setattr(container_module, "build_server_manager", EmptyToolsServerManager)
    monkeypatch.setattr(
        container_module,
        "build_tools_client_factory",
        lambda: cli_tools.MCPToolsClientFactory(client_class=cast("Any", EmptyToolsClient)),
    )
    empty = runner.invoke(cli.app, ["tools", "list"])
    assert empty.exit_code == 0
    assert "No tools are currently exposed" in empty.stdout

    for server_status, message in [
        ({"running": False}, "Managed server is not running"),
        ({"running": True, "healthy": False}, "Managed server is not healthy"),
        ({"running": True, "healthy": True}, "did not include an MCP URL"),
    ]:
        monkeypatch.setattr(
            container_module,
            "build_server_manager",
            server_manager_for_status(server_status),
        )
        failed = runner.invoke(cli.app, ["tools", "list"])
        assert failed.exit_code == 1
        assert message in failed.stderr


def test_tool_call_output_helpers() -> None:
    output = StringIO()
    presenter = cli_tools.ToolsPresenter(
        console=Console(file=output, force_terminal=False, color_system=None, width=100),
    )

    presenter.tool_call_result({"value": 1}, output=cli_tools.ToolOutput.text)
    presenter.tool_call_result(
        {"content": [{"type": "image", "data": "raw"}]},
        output=cli_tools.ToolOutput.text,
    )
    presenter.tool_call_result(
        {"content": [{"type": "text", "text": "json"}], "isError": False},
        output=cli_tools.ToolOutput.json,
    )
    presenter.tool_call_result({"content": []}, output=cli_tools.ToolOutput.text)
    presenter.warning("warn", "details")

    rendered = output.getvalue()
    assert '{"value": 1}' in rendered
    assert '{"type": "image", "data": "raw"}' in rendered
    assert '"isError": false' in rendered
    assert "details" in rendered
    assert cli_tools.tool_output_shape({"name": None}) is None
    assert cli_tools.find_tool_descriptor([], "missing") is None
    assert cli_tools.mcp_tool_result_shape()["content"][0]["text"] == "..."


def test_cli_presenter_and_factories_cover_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_container = object()

    class FakeHttpContainerModule:
        def get_container(self) -> object:
            return fake_container

    _, presenter = capture_console()

    assert "Not available" in cast("Text", presenter.render_value(None)).plain
    assert not cli_tools.tool_result_text({"content": []})
    assert cli_tools.tool_result_text({"content": ["raw"]}) == '"raw"'
    assert isinstance(container_module.build_server_manager(), cli_tools.ServerManager)
    assert isinstance(
        container_module.build_tools_client_factory(),
        cli_tools.MCPToolsClientFactory,
    )
    monkeypatch.setattr(container_module, "import_module", lambda _name: FakeHttpContainerModule())
    assert container_module.get_container() is fake_container


def test_server_status_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    output, presenter = capture_console()

    server_presenter = ServerPresenter(base=presenter)
    server_presenter.status(
        {
            "running": True,
            "healthy": True,
            "base_url": "http://127.0.0.1:45218",
            "mcp_url": "http://127.0.0.1:45218/mcp",
            "pid": 123,
            "state_path": "run/server.json",
            "log_path": "logs/server.log",
        },
    )
    server_presenter.status({"running": False, "state_path": "run/server.json"})
    presenter.success("Done", "detail line")

    rendered = output.getvalue()
    assert "Healthy" in rendered
    assert "http://127.0.0.1:45218/mcp" in rendered
    assert "run/server.json" in rendered
    assert "logs/server.log" in rendered
    assert "detail line" in rendered


def test_server_stop_error_and_not_running_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class StopErrorServer(FakeServerManager):
        def stop(self, *, force: bool) -> bool:
            raise ServerError("stop failed")

        def status(self) -> dict[str, Any]:
            return {"running": False}

    fake = StopErrorServer()
    monkeypatch.setattr(
        server_commands,
        "ServerCommandService",
        lambda: command_services.ServerCommandService(manager=cast("Any", fake)),
    )

    failed = runner.invoke(cli.app, ["server", "stop"])
    assert failed.exit_code == 1
    assert "stop failed" in failed.stderr

    status = runner.invoke(cli.app, ["server", "status"])
    assert status.exit_code == 0
    assert "Not running" in status.stdout


def test_main_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_app() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "app", fake_app)
    cli.main()
    assert called
