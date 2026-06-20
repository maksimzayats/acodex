from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from acodex.cli import __main__ as cli
from acodex.cli.codex import CodexAppError
from acodex.cli.server import ServerError, ServerState
from acodex.config import AcodexConfig

runner = CliRunner()


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
                    "detail": "http://127.0.0.1:8765",
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
        return {"running": True, "healthy": False, "base_url": "http://127.0.0.1:8765"}

    def tail_logs(self, *, tail: int) -> tuple[Path, list[str]]:
        if tail == 1:
            return Path("server.log"), ["last"]
        return Path("server.log"), []


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
    assert json.loads(show.stdout)["server"]["port"] == 8765


def test_config_show_invalid_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("ACODEX_CONFIG", str(path))

    result = runner.invoke(cli.app, ["config", "show"])

    assert result.exit_code == 1
    assert "Invalid JSON" in result.stderr


def test_doctor_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "Doctor", FakeDoctor)

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
    monkeypatch.setattr(cli, "Doctor", FakeDoctorWithFix)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "Suggested fixes" in result.stdout
    assert "Start the managed acodex HTTP server" in result.stdout
    assert "acodex server start" in result.stdout


def test_codex_status_and_relaunch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCodexManager()
    path = tmp_path / "config.json"
    monkeypatch.setenv("ACODEX_CONFIG", str(path))
    monkeypatch.setattr(cli, "CodexAppManager", lambda: fake)

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


def test_codex_status_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.json"
    path.write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("ACODEX_CONFIG", str(path))

    result = runner.invoke(cli.app, ["codex", "status"])

    assert result.exit_code == 1
    assert "Invalid JSON" in result.stderr


def test_server_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeServerManager()
    monkeypatch.setenv("ACODEX_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(cli, "ServerManager", lambda: fake)

    start = runner.invoke(cli.app, ["server", "start", "--host", "127.0.0.2", "--port", "9000"])
    assert start.exit_code == 0
    assert "Managed Server Started" in start.stdout
    assert "HTTP" in start.stdout
    assert "http://127.0.0.2:9000" in start.stdout

    failed = runner.invoke(cli.app, ["server", "start", "--host", "fail"])
    assert failed.exit_code == 1
    assert "start failed" in failed.stderr

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


def test_server_stop_error_and_not_running_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class StopErrorServer(FakeServerManager):
        def stop(self, *, force: bool) -> bool:
            raise ServerError("stop failed")

        def status(self) -> dict[str, Any]:
            return {"running": False}

    fake = StopErrorServer()
    monkeypatch.setattr(cli, "ServerManager", lambda: fake)

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
