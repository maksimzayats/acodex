from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer

from acodex.cli.codex import CodexAppError, CodexAppManager
from acodex.cli.doctor import Doctor
from acodex.cli.presenters.base import CliPresenter
from acodex.cli.presenters.codex import CodexPresenter
from acodex.cli.presenters.doctor import DoctorPresenter
from acodex.cli.presenters.server import ServerPresenter
from acodex.cli.server import ServerError, ServerManager
from acodex.config import ConfigError, get_config_path, init_config, load_config


@dataclass(kw_only=True, slots=True)
class ConfigCommandService:
    """Behavior for `acodex config` commands."""

    presenter: CliPresenter = field(default_factory=CliPresenter)

    def path(self) -> None:
        """Print the effective config path."""
        self.presenter.console.print(
            str(get_config_path()),
            style="cyan",
            highlight=False,
            soft_wrap=True,
        )

    def show(self) -> None:
        """Print the effective config."""
        try:
            self.presenter.json(load_config().model_dump(mode="json"))
        except ConfigError as exc:
            self.presenter.fail(str(exc))

    def init(self) -> None:
        """Initialize the config file if needed."""
        config_path = init_config()
        self.presenter.key_values(
            "Configuration",
            [("Status", "Ready"), ("Path", str(config_path))],
        )


@dataclass(kw_only=True, slots=True)
class DoctorCommandService:
    """Behavior for `acodex doctor`."""

    doctor: Doctor = field(default_factory=Doctor)
    presenter: DoctorPresenter = field(default_factory=DoctorPresenter)
    base_presenter: CliPresenter = field(default_factory=CliPresenter)

    def run(self, *, json_output: bool, deep: bool) -> None:
        """Run diagnostics and render the result."""
        doctor_result = self.doctor.run(deep=deep)
        if json_output:
            self.base_presenter.json(doctor_result)
        else:
            self.presenter.result(doctor_result)
        if not doctor_result["ok"]:
            raise typer.Exit(1)


@dataclass(kw_only=True, slots=True)
class CodexCommandService:
    """Behavior for `acodex codex` commands."""

    manager: CodexAppManager = field(default_factory=CodexAppManager)
    presenter: CodexPresenter = field(default_factory=CodexPresenter)
    base_presenter: CliPresenter = field(default_factory=CliPresenter)

    def status(self) -> None:
        """Render Codex app status."""
        try:
            self.presenter.status(self.manager.status(load_config()))
        except ConfigError as exc:
            self.base_presenter.fail(str(exc))

    def relaunch(self, *, app_path: Path | None, port: int | None, yes: bool) -> None:
        """Relaunch Codex with the configured CDP port."""
        try:
            self.base_presenter.success(self._relaunch(app_path=app_path, port=port, yes=yes))
        except (ConfigError, CodexAppError) as exc:
            self.base_presenter.fail(str(exc))

    def _relaunch(self, *, app_path: Path | None, port: int | None, yes: bool) -> str:
        codex_app_path = None
        if app_path is not None:
            codex_app_path = str(app_path)
        config = load_config(
            codex_app_path=codex_app_path,
            cdp_port=port,
        )
        app_status = self.manager.status(config)
        confirmed = yes
        if self._needs_relaunch_confirmation(app_status, config.codex.cdp_port, yes=yes):
            confirmed = typer.confirm(
                "Codex is running without the configured CDP port. Quit and relaunch it?",
            )
        return self.manager.relaunch(config, confirmed=confirmed)

    def _needs_relaunch_confirmation(
        self,
        app_status: dict[str, object],
        cdp_port: int,
        *,
        yes: bool,
    ) -> bool:
        return (
            bool(app_status["running"]) and app_status["detected_cdp_port"] != cdp_port and not yes
        )


@dataclass(kw_only=True, slots=True)
class ServerCommandService:
    """Behavior for `acodex server` commands."""

    manager: ServerManager = field(default_factory=ServerManager)
    presenter: ServerPresenter = field(default_factory=ServerPresenter)
    base_presenter: CliPresenter = field(default_factory=CliPresenter)

    def start(self, *, host: str | None, port: int | None) -> None:
        """Start the managed server."""
        try:
            config = load_config(server_host=host, server_port=port)
            server_state = self.manager.start(config)
        except (ConfigError, ServerError) as exc:
            self.base_presenter.fail(str(exc))
        self.presenter.started(
            base_url=server_state.base_url,
            mcp_url=server_state.mcp_url,
            pid=server_state.pid,
            log_path=server_state.log_path,
        )

    def stop(self, *, force: bool) -> None:
        """Stop the managed server."""
        try:
            stopped = self.manager.stop(force=force)
        except ServerError as exc:
            self.base_presenter.fail(str(exc))
        if stopped:
            self.base_presenter.success("Stopped managed server")
            return
        self.base_presenter.warning("Managed server is not running")

    def status(self, *, json_output: bool) -> None:
        """Render managed server status."""
        server_status = self.manager.status()
        if json_output:
            self.base_presenter.json(server_status)
            return
        self.presenter.status(server_status)

    def logs(self, *, tail: int) -> None:
        """Render managed server logs."""
        log_path, log_lines = self.manager.tail_logs(tail=tail)
        self.presenter.logs(log_path, log_lines)
