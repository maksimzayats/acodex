from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acodex.cli.codex import CodexAppManager
from acodex.cli.server import ServerManager
from acodex.config import AcodexConfig, ConfigError, get_config_path, load_config

CHECK_PASS = "pass"  # noqa: S105 - doctor check status, not a password.
CHECK_WARN = "warn"
CHECK_FAIL = "fail"


@dataclass(frozen=True, kw_only=True, slots=True)
class DoctorFix:
    summary: str
    command: str | None = None
    detail: str | None = None

    def to_json(self) -> dict[str, str]:
        """Serialize a remediation hint for machine-readable doctor output.

        Returns:
            JSON-compatible fix payload.

        """
        payload = {"summary": self.summary}
        if self.command is not None:
            payload["command"] = self.command
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True, kw_only=True, slots=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    fix: DoctorFix | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize the check for machine-readable doctor output.

        Returns:
            JSON-compatible check payload.

        """
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.fix is not None:
            payload["fix"] = self.fix.to_json()
        return payload


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
            checks.append(DoctorCheck(name="config", status=CHECK_PASS, detail="config loaded"))
        except ConfigError as exc:
            config_path = self.config_path or get_config_path()
            checks.append(
                DoctorCheck(
                    name="config",
                    status=CHECK_FAIL,
                    detail=str(exc),
                    fix=DoctorFix(
                        summary="Move the invalid config aside and recreate the default file.",
                        command=_join_commands(
                            [
                                "mv",
                                str(config_path),
                                f"{config_path}.bak",
                            ],
                            ["acodex", "config", "init"],
                        ),
                        detail=f"Review {config_path}.bak before restoring custom settings.",
                    ),
                ),
            )
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
        app_exists = bool(status["app_exists"])
        running = bool(status["running"])
        cdp_reachable = bool(status["cdp_reachable"])
        app_status = CHECK_PASS if app_exists else CHECK_WARN
        running_status = CHECK_PASS if running else CHECK_WARN
        cdp_status = CHECK_PASS if cdp_reachable else CHECK_WARN
        return [
            DoctorCheck(
                name="codex-app",
                status=app_status,
                detail=str(status["app_path"]),
                fix=None if app_exists else _configure_codex_app_fix(),
            ),
            DoctorCheck(
                name="codex-process",
                status=running_status,
                detail="running" if running else "not running",
                fix=None if running else _codex_relaunch_fix(app_exists=app_exists),
            ),
            DoctorCheck(
                name="codex-cdp",
                status=cdp_status,
                detail=status["configured_cdp_url"],
                fix=None if cdp_reachable else _codex_relaunch_fix(app_exists=app_exists),
            ),
        ]

    def _server_checks(self, config: AcodexConfig, *, deep: bool) -> list[DoctorCheck]:
        manager = self._server_manager()
        status = manager.status()
        running = bool(status["running"])
        healthy = bool(status.get("healthy"))
        checks = [
            DoctorCheck(
                name="server",
                status=CHECK_PASS if running else CHECK_WARN,
                detail=str(
                    status.get(
                        "base_url",
                        "http://{}:{}".format(config.server.host, config.server.port),
                    ),
                ),
                fix=None if running else _server_start_fix(config),
            ),
            DoctorCheck(
                name="server-healthz",
                status=CHECK_PASS if healthy else CHECK_WARN,
                detail="/healthz",
                fix=self._server_health_fix(config, healthy=healthy, running=running),
            ),
        ]
        if deep and healthy and isinstance(status.get("mcp_url"), str):
            mcp_ok = manager.http_probe.mcp_initialize(
                status["mcp_url"],
                timeout=config.codex.request_timeout,
            )
            checks.append(
                DoctorCheck(
                    name="server-mcp",
                    status=CHECK_PASS if mcp_ok else CHECK_FAIL,
                    detail=status["mcp_url"],
                    fix=None if mcp_ok else _server_restart_fix(config),
                ),
            )
        return checks

    def _server_manager(self) -> ServerManager:
        if self.server_manager is None:
            self.server_manager = ServerManager(config_path=self.config_path)
        return self.server_manager

    def _server_health_fix(
        self,
        config: AcodexConfig,
        *,
        healthy: bool,
        running: bool,
    ) -> DoctorFix | None:
        if healthy:
            return None
        if running:
            return _server_restart_fix(config)
        return _server_start_fix(config)


def _result(checks: list[DoctorCheck]) -> dict[str, Any]:
    return {
        "ok": all(check.status != CHECK_FAIL for check in checks),
        "checks": [check.to_json() for check in checks],
    }


def _check_writable_directory(name: str, path: Path) -> DoctorCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DoctorCheck(
            name=name,
            status=CHECK_FAIL,
            detail=str(exc),
            fix=DoctorFix(
                summary="Create the directory and make sure your user can write to it.",
                command=_join_shell(["mkdir", "-p", str(path)]),
            ),
        )
    return DoctorCheck(name=name, status=CHECK_PASS, detail=str(path))


def _configure_codex_app_fix() -> DoctorFix:
    return DoctorFix(
        summary="Point acodex at the installed Codex.app bundle.",
        command="ACODEX_CODEX_APP_PATH=/path/to/Codex.app acodex codex relaunch --yes",
        detail="Use the real app bundle path if Codex is installed somewhere else.",
    )


def _codex_relaunch_fix(*, app_exists: bool) -> DoctorFix:
    if not app_exists:
        return _configure_codex_app_fix()
    return DoctorFix(
        summary="Launch or relaunch Codex with the configured CDP port.",
        command=_acodex_command("codex", "relaunch", "--yes"),
    )


def _server_start_fix(config: AcodexConfig) -> DoctorFix:
    return DoctorFix(
        summary="Start the managed acodex HTTP server.",
        command=_acodex_command(
            "server",
            "start",
            "--host",
            config.server.host,
            "--port",
            str(config.server.port),
        ),
    )


def _server_restart_fix(config: AcodexConfig) -> DoctorFix:
    return DoctorFix(
        summary="Restart the managed acodex HTTP server.",
        command=(
            "{} && {}".format(
                _acodex_command("server", "stop", "--force"),
                _acodex_command(
                    "server",
                    "start",
                    "--host",
                    config.server.host,
                    "--port",
                    str(config.server.port),
                ),
            )
        ),
    )


def _acodex_command(*parts: str) -> str:
    return _join_shell(["acodex", *parts])


def _join_shell(parts: list[str]) -> str:
    return shlex.join(parts)


def _join_commands(*commands: list[str]) -> str:
    return " && ".join(_join_shell(command) for command in commands)
