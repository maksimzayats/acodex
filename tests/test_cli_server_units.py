from __future__ import annotations

import os
from pathlib import Path
from typing import Any, BinaryIO, cast

import pytest
from typing_extensions import Self

from acodex.cli import server as server_module
from acodex.cli.server import HttpProbe, ProcessOps, ServerError, ServerManager, ServerState
from acodex.config import AcodexConfig, ServerConfig


class FakeProcessOps(ProcessOps):
    def __init__(self) -> None:
        self.running: set[int] = set()
        self.spawned: list[list[str]] = []
        self.terminated: list[int] = []
        self.killed: list[int] = []
        self.next_pid = 123

    def is_running(self, pid: int) -> bool:
        return pid in self.running

    def spawn(self, command: list[str], log_file: BinaryIO) -> int:
        self.spawned.append(command)
        log_file.write(b"started\n")
        self.running.add(self.next_pid)
        return self.next_pid

    def terminate(self, pid: int) -> None:
        self.terminated.append(pid)
        self.running.discard(pid)

    def kill(self, pid: int) -> None:
        self.killed.append(pid)
        self.running.discard(pid)


class StickyProcessOps(FakeProcessOps):
    def terminate(self, pid: int) -> None:
        self.terminated.append(pid)


class FakeHttpProbe(HttpProbe):
    def __init__(self, *, reachable: bool = True, mcp_ok: bool = True) -> None:
        self.reachable_result = reachable
        self.mcp_ok = mcp_ok
        self.urls: list[str] = []
        self.mcp_urls: list[str] = []

    def reachable(self, url: str, *, timeout: float) -> bool:
        self.urls.append(url)
        return self.reachable_result

    def mcp_initialize(self, mcp_url: str, *, timeout: float) -> bool:
        self.mcp_urls.append(mcp_url)
        return self.mcp_ok


def manager(tmp_path: Path, *, process_ops: ProcessOps, probe: HttpProbe) -> ServerManager:
    return ServerManager(
        config_path=tmp_path / "config.json",
        process_ops=process_ops,
        http_probe=probe,
        poll_interval=0.0,
    )


def state(pid: int = 123) -> ServerState:
    return ServerState(
        pid=pid,
        host="127.0.0.1",
        port=8765,
        base_url="http://127.0.0.1:8765",
        mcp_url="http://127.0.0.1:8765/mcp",
        started_at=1.0,
        log_path="server.log",
        command=["uvicorn"],
    )


def test_server_start_writes_state_and_logs(tmp_path: Path) -> None:
    process_ops = FakeProcessOps()
    probe = FakeHttpProbe()
    server = manager(tmp_path, process_ops=process_ops, probe=probe)

    result = server.start(AcodexConfig())

    assert result.pid == 123
    assert result.base_url == "http://127.0.0.1:8765"
    assert result.mcp_url == "http://127.0.0.1:8765/mcp"
    assert process_ops.spawned[0][-2:] == ["--port", "8765"]
    assert server.read_state() == result
    assert server.paths.log_path.read_bytes() == b"started\n"
    assert probe.urls == ["http://127.0.0.1:8765/healthz"]


def test_server_start_handles_stale_and_running_state(tmp_path: Path) -> None:
    process_ops = FakeProcessOps()
    probe = FakeHttpProbe()
    server = manager(tmp_path, process_ops=process_ops, probe=probe)
    server.paths.state_path.parent.mkdir(parents=True)
    server._write_state(state(pid=999))

    assert server.start(AcodexConfig()).pid == 123

    with pytest.raises(ServerError, match="already running"):
        server.start(AcodexConfig())


def test_server_start_port_conflict_and_health_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = manager(tmp_path, process_ops=FakeProcessOps(), probe=FakeHttpProbe())
    monkeypatch.setattr(ServerManager, "_port_in_use", staticmethod(lambda _host, _port: True))
    with pytest.raises(ServerError, match="already in use"):
        server.start(AcodexConfig())

    failing_process_ops = FakeProcessOps()
    failing = manager(
        tmp_path,
        process_ops=failing_process_ops,
        probe=FakeHttpProbe(reachable=False),
    )
    monkeypatch.setattr(ServerManager, "_port_in_use", staticmethod(lambda _host, _port: False))
    with pytest.raises(ServerError, match="did not become healthy"):
        failing.start(AcodexConfig())
    assert failing_process_ops.terminated == [123]
    assert not failing.paths.state_path.exists()


def test_server_stop_paths(tmp_path: Path) -> None:
    process_ops = FakeProcessOps()
    server = manager(tmp_path, process_ops=process_ops, probe=FakeHttpProbe())

    assert not server.stop(force=False)

    server.paths.state_path.parent.mkdir(parents=True)
    server._write_state(state(pid=555))
    assert not server.stop(force=False)
    assert not server.paths.state_path.exists()

    server._write_state(state(pid=123))
    process_ops.running.add(123)
    assert server.stop(force=False)
    assert process_ops.terminated == [123]
    assert not server.paths.state_path.exists()


def test_server_stop_force(tmp_path: Path) -> None:
    process_ops = StickyProcessOps()
    process_ops.running.add(123)
    server = manager(tmp_path, process_ops=process_ops, probe=FakeHttpProbe())
    server.paths.state_path.parent.mkdir(parents=True)
    server._write_state(state())

    with pytest.raises(ServerError, match="--force"):
        server.stop(force=False)

    assert server.stop(force=True)
    assert process_ops.killed == [123]


def test_status_and_logs(tmp_path: Path) -> None:
    process_ops = FakeProcessOps()
    probe = FakeHttpProbe(reachable=True)
    server = manager(tmp_path, process_ops=process_ops, probe=probe)

    assert server.status()["running"] is False
    assert server.read_state() is None

    server.paths.state_path.parent.mkdir(parents=True)
    server.paths.log_path.parent.mkdir(parents=True)
    server.paths.log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    server._write_state(state())
    process_ops.running.add(123)

    status = server.status()
    assert status["running"] is True
    assert status["healthy"] is True
    assert status["base_url"] == "http://127.0.0.1:8765"
    assert server.tail_logs(tail=2)[1] == ["two", "three"]

    process_ops.running.clear()
    assert server.status()["running"] is False
    assert not server.paths.state_path.exists()

    server.paths.log_path.unlink()
    assert server.tail_logs(tail=2) == (server.paths.log_path, [])


def test_state_json_invalid_and_custom_config(tmp_path: Path) -> None:
    server = manager(tmp_path, process_ops=FakeProcessOps(), probe=FakeHttpProbe())
    server.paths.state_path.parent.mkdir(parents=True)
    server.paths.state_path.write_text("[]", encoding="utf-8")
    assert server.read_state() is None

    server.paths.state_path.write_text("{bad", encoding="utf-8")
    assert server.read_state() is None

    custom = AcodexConfig(server=ServerConfig(host="127.0.0.2", port=8899))
    assert custom.server.host == "127.0.0.2"


def test_process_ops_and_http_probe_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    ops = ProcessOps()
    assert not ops.is_running(-1)
    monkeypatch.setattr(os, "kill", lambda _pid, _sig: (_ for _ in ()).throw(ProcessLookupError()))
    assert not ops.is_running(123)
    monkeypatch.setattr(os, "kill", lambda _pid, _sig: (_ for _ in ()).throw(PermissionError()))
    assert ops.is_running(123)

    probe = HttpProbe()
    monkeypatch.setattr(
        "acodex.cli.server.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )
    assert not probe.reachable("http://127.0.0.1:1", timeout=0.1)
    assert not probe.mcp_initialize("http://127.0.0.1:1/mcp", timeout=0.1)


class BinaryLog:
    def write(self, data: bytes) -> int:
        return len(data)


def test_process_ops_and_http_probe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        pid = 321

    class FakeResponse:
        status = 204

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    popen_calls: list[dict[str, Any]] = []
    kill_calls: list[tuple[int, int]] = []

    def popen(command: list[str], **kwargs: Any) -> FakeProcess:
        popen_calls.append({"command": command, **kwargs})
        return FakeProcess()

    ops = ProcessOps()
    monkeypatch.setattr(server_module.subprocess, "Popen", popen)
    monkeypatch.setattr(os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    assert ops.is_running(321)
    assert ops.spawn(["uvicorn"], cast("BinaryIO", BinaryLog())) == 321
    ops.terminate(321)
    ops.kill(321)
    assert popen_calls[0]["command"] == ["uvicorn"]
    assert len(kill_calls) == 3

    monkeypatch.setattr(
        "acodex.cli.server.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    probe = HttpProbe()
    assert probe.reachable("http://127.0.0.1:8765/healthz", timeout=0.1)
    assert probe.mcp_initialize("http://127.0.0.1:8765/mcp", timeout=0.1)


def test_state_from_json_defaults_command() -> None:
    payload: dict[str, Any] = {
        "pid": "1",
        "host": "h",
        "port": "2",
        "base_url": "b",
        "mcp_url": "m",
        "started_at": "3.0",
        "log_path": "l",
    }
    assert ServerState.from_json(payload).command == []


def test_wait_for_health_exit_and_timeout(tmp_path: Path) -> None:
    process_ops = FakeProcessOps()
    server = manager(
        tmp_path,
        process_ops=process_ops,
        probe=FakeHttpProbe(reachable=False),
    )

    assert not server.wait_for_health(state(), timeout=0.01)

    process_ops.running.add(123)
    assert not server.wait_for_health(state(), timeout=0.0)
