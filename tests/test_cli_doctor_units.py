from __future__ import annotations

import json
from pathlib import Path

import pytest

from acodex.cli.codex import CodexAppManager
from acodex.cli.doctor import Doctor, _check_writable_directory
from acodex.cli.server import HttpProbe, ServerManager
from acodex.config import AcodexConfig


class FakeCodexManager(CodexAppManager):
    def __init__(self, *, exists: bool = True, running: bool = True, cdp: bool = True) -> None:
        self.exists = exists
        self.running = running
        self.cdp = cdp

    def status(self, config: AcodexConfig) -> dict[str, object]:
        return {
            "app_path": config.codex.app_path,
            "app_exists": self.exists,
            "running": self.running,
            "pid": 1 if self.running else None,
            "detected_cdp_port": config.codex.cdp_port if self.running else None,
            "configured_cdp_url": config.codex.cdp_url,
            "cdp_reachable": self.cdp,
        }


class FakeProbe(HttpProbe):
    def __init__(self, *, mcp_ok: bool = True) -> None:
        self.mcp_ok = mcp_ok

    def mcp_initialize(self, mcp_url: str, *, timeout: float) -> bool:
        return self.mcp_ok


class FakeServerManager(ServerManager):
    def __init__(self, config_path: Path, *, running: bool = True, healthy: bool = True) -> None:
        super().__init__(config_path=config_path)
        self.running = running
        self.healthy = healthy
        self.http_probe = FakeProbe()

    def status(self) -> dict[str, object]:
        return {
            "running": self.running,
            "managed": self.running,
            "healthy": self.healthy,
            "base_url": "http://127.0.0.1:8765",
            "mcp_url": "http://127.0.0.1:8765/mcp",
        }


def test_doctor_reports_checks_and_deep_mcp(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    server = FakeServerManager(path, running=True, healthy=True)
    doctor = Doctor(
        config_path=path,
        codex_manager=FakeCodexManager(),
        server_manager=server,
    )

    result = doctor.run(deep=True)

    assert result["ok"] is True
    names = [check["name"] for check in result["checks"]]
    assert "config" in names
    assert "server-mcp" in names
    assert (tmp_path / "run").exists()
    assert (tmp_path / "logs").exists()


def test_doctor_warns_without_running_services(tmp_path: Path) -> None:
    result = Doctor(
        config_path=tmp_path / "config.json",
        codex_manager=FakeCodexManager(exists=False, running=False, cdp=False),
        server_manager=FakeServerManager(tmp_path / "config.json", running=False, healthy=False),
    ).run(deep=True)

    assert result["ok"] is True
    statuses = {check["name"]: check["status"] for check in result["checks"]}
    assert statuses["codex-app"] == "warn"
    assert statuses["server"] == "warn"
    assert "server-mcp" not in statuses


def test_doctor_fails_invalid_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"bad": True}), encoding="utf-8")

    result = Doctor(config_path=path, codex_manager=FakeCodexManager()).run(deep=False)

    assert result["ok"] is False
    assert result["checks"][0]["name"] == "config"
    assert result["checks"][0]["status"] == "fail"


def test_doctor_default_server_manager_and_directory_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doctor = Doctor(config_path=tmp_path / "config.json", codex_manager=FakeCodexManager())
    assert doctor._server_manager() is doctor._server_manager()

    monkeypatch.setattr(
        Path,
        "mkdir",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no")),
    )
    check = _check_writable_directory("bad-dir", tmp_path / "blocked")
    assert check.status == "fail"
