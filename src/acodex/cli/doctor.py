from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acodex.cli.codex import CodexAppManager
from acodex.cli.server import ServerManager
from acodex.config import AcodexConfig, ConfigError, load_config


@dataclass(frozen=True, kw_only=True, slots=True)
class DoctorCheck:
    name: str
    status: str
    detail: str

    def to_json(self) -> dict[str, str]:
        """Serialize the check for machine-readable doctor output.

        Returns:
            JSON-compatible check payload.

        """
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(kw_only=True, slots=True)
class Doctor:
    config_path: Path | None = None
    codex_manager: CodexAppManager = field(default_factory=CodexAppManager)
    server_manager: ServerManager | None = None

    def run(self, *, deep: bool) -> dict[str, Any]:
        """Run doctor checks and return a stable JSON-compatible payload.

        Returns:
            Doctor result with an ok flag and check list.

        """
        checks: list[DoctorCheck] = []
        try:
            config = load_config(config_path=self.config_path)
            checks.append(DoctorCheck(name="config", status="pass", detail="config loaded"))
        except ConfigError as exc:
            checks.append(DoctorCheck(name="config", status="fail", detail=str(exc)))
            return _result(checks)

        checks.extend(self._filesystem_checks())
        checks.extend(self._codex_checks(config))
        checks.extend(self._server_checks(config, deep=deep))
        return _result(checks)

    def _filesystem_checks(self) -> list[DoctorCheck]:
        manager = self._server_manager()
        checks: list[DoctorCheck] = []
        for name, path in {
            "config-dir": manager.paths.state_path.parent.parent,
            "runtime-dir": manager.paths.state_path.parent,
            "logs-dir": manager.paths.log_path.parent,
        }.items():
            checks.append(_check_writable_directory(name, path))
        return checks

    def _codex_checks(self, config: AcodexConfig) -> list[DoctorCheck]:
        status = self.codex_manager.status(config)
        app_status = "pass" if status["app_exists"] else "warn"
        running_status = "pass" if status["running"] else "warn"
        cdp_status = "pass" if status["cdp_reachable"] else "warn"
        return [
            DoctorCheck(name="codex-app", status=app_status, detail=str(status["app_path"])),
            DoctorCheck(
                name="codex-process",
                status=running_status,
                detail="running" if status["running"] else "not running",
            ),
            DoctorCheck(
                name="codex-cdp",
                status=cdp_status,
                detail=status["configured_cdp_url"],
            ),
        ]

    def _server_checks(self, config: AcodexConfig, *, deep: bool) -> list[DoctorCheck]:
        manager = self._server_manager()
        status = manager.status()
        checks = [
            DoctorCheck(
                name="server",
                status="pass" if status["running"] else "warn",
                detail=str(
                    status.get("base_url", f"http://{config.server.host}:{config.server.port}"),
                ),
            ),
            DoctorCheck(
                name="server-healthz",
                status="pass" if status.get("healthy") else "warn",
                detail="/healthz",
            ),
        ]
        if deep and status.get("healthy") and isinstance(status.get("mcp_url"), str):
            mcp_ok = manager.http_probe.mcp_initialize(
                status["mcp_url"],
                timeout=config.codex.request_timeout,
            )
            checks.append(
                DoctorCheck(
                    name="server-mcp",
                    status="pass" if mcp_ok else "fail",
                    detail=status["mcp_url"],
                ),
            )
        return checks

    def _server_manager(self) -> ServerManager:
        if self.server_manager is None:
            self.server_manager = ServerManager(config_path=self.config_path)
        return self.server_manager


def _result(checks: list[DoctorCheck]) -> dict[str, Any]:
    return {
        "ok": all(check.status != "fail" for check in checks),
        "checks": [check.to_json() for check in checks],
    }


def _check_writable_directory(name: str, path: Path) -> DoctorCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DoctorCheck(name=name, status="fail", detail=str(exc))
    return DoctorCheck(name=name, status="pass", detail=str(path))
