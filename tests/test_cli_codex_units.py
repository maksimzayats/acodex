from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typing_extensions import Self

from acodex.cli import codex as codex_module
from acodex.cli.codex import (
    CDPProbe,
    CodexAppError,
    CodexAppManager,
    CodexSystemOps,
    ProcessInfo,
    detect_cdp_port,
)
from acodex.config import AcodexConfig, CodexConfig


class FakeSystemOps(CodexSystemOps):
    def __init__(self, processes: list[ProcessInfo] | None = None, *, exists: bool = True) -> None:
        self.processes = processes or []
        self.exists = exists
        self.launched: list[tuple[str, int]] = []
        self.quit_calls = 0

    def list_processes(self) -> list[ProcessInfo]:
        return list(self.processes)

    def app_exists(self, app_path: str) -> bool:
        return self.exists

    def quit_app(self) -> None:
        self.quit_calls += 1
        self.processes = []

    def launch_app(self, app_path: str, *, port: int) -> None:
        self.launched.append((app_path, port))


class FakeCDPProbe(CDPProbe):
    def __init__(self, results: list[bool] | None = None) -> None:
        self.results = results or [True]
        self.urls: list[str] = []

    def reachable(self, base_url: str, *, timeout: float) -> bool:
        self.urls.append(base_url)
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def config() -> AcodexConfig:
    return AcodexConfig(codex=CodexConfig(app_path="/Applications/Codex.app", launch_timeout=0.01))


def timeout_config() -> AcodexConfig:
    return AcodexConfig(codex=CodexConfig(app_path="/Applications/Codex.app", launch_timeout=0.0))


def test_detect_cdp_port() -> None:
    assert detect_cdp_port("--remote-debugging-port=45217") == 45217
    assert detect_cdp_port("--remote-debugging-port 45218") == 45218
    assert detect_cdp_port("no port") is None


def test_status_reports_process_and_cdp() -> None:
    ops = FakeSystemOps([
        ProcessInfo(
            pid=42,
            command="/Applications/Codex.app/Contents/MacOS/Codex --remote-debugging-port=45217",
        ),
    ])
    probe = FakeCDPProbe([True])
    manager = CodexAppManager(system_ops=ops, cdp_probe=probe, poll_interval=0.0)

    status = manager.status(config())

    assert status["app_exists"] is True
    assert status["running"] is True
    assert status["pid"] == 42
    assert status["detected_cdp_port"] == 45217
    assert status["configured_cdp_url"] == "http://127.0.0.1:45217"
    assert status["cdp_reachable"] is True


def test_relaunch_noops_when_port_matches() -> None:
    ops = FakeSystemOps([
        ProcessInfo(
            pid=1,
            command="/Applications/Codex.app/Contents/MacOS/Codex --remote-debugging-port=45217",
        ),
    ])
    manager = CodexAppManager(system_ops=ops, cdp_probe=FakeCDPProbe(), poll_interval=0.0)

    assert (
        manager.relaunch(config(), confirmed=False) == "Codex is already running with CDP port 45217"
    )
    assert ops.launched == []


def test_relaunch_requires_confirmation_and_restarts() -> None:
    ops = FakeSystemOps([
        ProcessInfo(pid=1, command="/Applications/Codex.app/Contents/MacOS/Codex"),
    ])
    manager = CodexAppManager(
        system_ops=ops,
        cdp_probe=FakeCDPProbe([True]),
        poll_interval=0.0,
    )

    with pytest.raises(CodexAppError, match="without the configured"):
        manager.relaunch(config(), confirmed=False)

    assert manager.relaunch(config(), confirmed=True) == "Codex launched with CDP port 45217"
    assert ops.quit_calls == 1
    assert ops.launched == [("/Applications/Codex.app", 45217)]


def test_relaunch_launches_when_not_running_and_handles_timeout() -> None:
    ops = FakeSystemOps([])
    manager = CodexAppManager(system_ops=ops, cdp_probe=FakeCDPProbe([True]), poll_interval=0.0)

    assert manager.relaunch(config(), confirmed=False) == "Codex launched with CDP port 45217"

    failing = CodexAppManager(system_ops=ops, cdp_probe=FakeCDPProbe([False]), poll_interval=0.0)
    with pytest.raises(CodexAppError, match="did not become reachable"):
        failing.relaunch(timeout_config(), confirmed=False)


def test_find_codex_process_matches_variants() -> None:
    manager = CodexAppManager(
        system_ops=FakeSystemOps(
            [
                ProcessInfo(pid=1, command="python something"),
                ProcessInfo(pid=2, command="/Users/me/Documents/Codex/other-process"),
                ProcessInfo(
                    pid=3,
                    command=(
                        "/Applications/Codex.app/Contents/Resources/codex app-server "
                        "--analytics-default-enabled"
                    ),
                ),
                ProcessInfo(
                    pid=4,
                    command="/Applications/Codex.app/Contents/MacOS/Codex --flag",
                ),
            ],
        ),
    )
    process = manager.find_codex_process("/Applications/Codex.app")
    assert process is not None
    assert process.pid == 4

    missing = CodexAppManager(
        system_ops=FakeSystemOps(
            [
                ProcessInfo(pid=1, command="python"),
                ProcessInfo(
                    pid=2,
                    command="/Applications/Codex.app/Contents/Resources/codex app-server",
                ),
                ProcessInfo(pid=3, command="/Applications/Other.app/Contents/MacOS/Codex"),
            ],
        ),
    )
    assert missing.find_codex_process("/Applications/Codex.app") is None


def test_relaunch_ignores_stale_codex_helper_processes() -> None:
    ops = FakeSystemOps(
        [
            ProcessInfo(
                pid=1,
                command="/Applications/Codex.app/Contents/Resources/codex app-server",
            ),
        ],
    )
    manager = CodexAppManager(system_ops=ops, cdp_probe=FakeCDPProbe([True]), poll_interval=0.0)

    assert manager.relaunch(config(), confirmed=False) == "Codex launched with CDP port 45217"
    assert ops.quit_calls == 0
    assert ops.launched == [("/Applications/Codex.app", 45217)]


def test_system_ops_and_cdp_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Completed:
        stdout = "  10 /Applications/Codex.app --remote-debugging-port=45217\n\nbad\n"

    class FakeResponse:
        status = 204

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> Completed:
        calls.append(command)
        return Completed()

    monkeypatch.setattr(codex_module.subprocess, "run", run)
    ops = CodexSystemOps()
    assert ops.list_processes() == [
        ProcessInfo(pid=10, command="/Applications/Codex.app --remote-debugging-port=45217"),
    ]
    app = tmp_path / "Codex.app"
    app.mkdir()
    assert ops.app_exists(str(app))
    ops.quit_app()
    ops.launch_app(str(app), port=45217)
    assert calls[1][0] == "/usr/bin/osascript"
    assert calls[2][0] == "/usr/bin/open"

    probe = CDPProbe()
    monkeypatch.setattr(
        "acodex.cli.codex.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )
    assert not probe.reachable("http://127.0.0.1:45217", timeout=0.1)

    monkeypatch.setattr(
        "acodex.cli.codex.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    assert probe.reachable("http://127.0.0.1:45217", timeout=0.1)


def test_wait_until_stopped_polls_until_process_disappears() -> None:
    class PollingManager(CodexAppManager):
        calls = 0

        def find_codex_process(self, app_path: str) -> ProcessInfo | None:
            self.calls += 1
            if self.calls == 1:
                return ProcessInfo(pid=1, command="Codex.app")
            return None

    manager = PollingManager(
        system_ops=FakeSystemOps(),
        cdp_probe=FakeCDPProbe(),
        poll_interval=0.0,
    )
    manager._wait_until_stopped("/Applications/Codex.app", timeout=0.01)
    assert manager.calls == 2


def test_wait_for_cdp_retries_and_wait_until_stopped_timeout() -> None:
    manager = CodexAppManager(
        system_ops=FakeSystemOps(),
        cdp_probe=FakeCDPProbe([False, True]),
        poll_interval=0.0,
    )

    assert manager.wait_for_cdp(config())
    manager._wait_until_stopped("/Applications/Codex.app", timeout=0.0)
