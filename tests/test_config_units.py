from __future__ import annotations

import json
from pathlib import Path

import pytest

from acodex import config as config_module
from acodex.config import (
    ConfigError,
    ConfigMerger,
    default_config,
    get_config_path,
    init_config,
    load_config,
)


def test_default_config_shape_and_settings() -> None:
    config = default_config()

    assert config.model_dump(mode="json") == {
        "server": {"host": "127.0.0.1", "port": 45218},
        "codex": {
            "app_path": "/Applications/Codex.app",
            "cdp_host": "127.0.0.1",
            "cdp_port": 45217,
            "request_timeout": 10.0,
            "launch_timeout": 20.0,
        },
        "bridge": {"host_id": "local", "source_thread_id": None},
    }
    assert config.codex.cdp_url == "http://127.0.0.1:45217"
    assert config.to_cdp_settings().base_url == "http://127.0.0.1:45217"
    assert config.to_bridge_settings().host_id == "local"


def test_config_path_env_and_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "custom" / "config.json"
    monkeypatch.setenv("ACODEX_CONFIG", str(path))

    assert get_config_path() == path
    assert config_module.config_root() == path.parent
    assert init_config() == path
    assert path.exists()
    assert init_config() == path


def test_load_config_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "server": {"host": "127.0.0.2", "port": 8000},
                "codex": {
                    "app_path": "/Applications/File.app",
                    "cdp_host": "file-host",
                    "cdp_port": 6000,
                    "request_timeout": 1.5,
                    "launch_timeout": 2.5,
                },
                "bridge": {"host_id": "file-host-id", "source_thread_id": "file-thread"},
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACODEX_SERVER_HOST", "env-host")
    monkeypatch.setenv("ACODEX_SERVER_PORT", "9000")
    monkeypatch.setenv("ACODEX_CODEX_APP_PATH", "/Applications/Env.app")
    monkeypatch.setenv("ACODEX_CODEX_APP_CDP_HOST", "env-cdp")
    monkeypatch.setenv("ACODEX_CODEX_APP_CDP_PORT", "7000")
    monkeypatch.setenv("ACODEX_CODEX_APP_CDP_REQUEST_TIMEOUT", "3.5")
    monkeypatch.setenv("ACODEX_CODEX_APP_BRIDGE_HOST_ID", "env-host-id")
    monkeypatch.setenv("ACODEX_CODEX_APP_BRIDGE_SOURCE_THREAD_ID", "env-thread")

    config = load_config(
        config_path=path,
        server_host="cli-host",
        server_port=9100,
        codex_app_path="/Applications/Cli.app",
        cdp_port=7100,
    )

    assert config.server.host == "cli-host"
    assert config.server.port == 9100
    assert config.codex.app_path == "/Applications/Cli.app"
    assert config.codex.cdp_host == "env-cdp"
    assert config.codex.cdp_port == 7100
    assert config.codex.request_timeout == pytest.approx(3.5)
    assert config.codex.launch_timeout == pytest.approx(2.5)
    assert config.bridge.host_id == "env-host-id"
    assert config.bridge.source_thread_id == "env-thread"


def test_invalid_config_errors(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{bad", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid JSON"):
        load_config(config_path=invalid)

    non_object = tmp_path / "array.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_config(config_path=non_object)

    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps({"unknown": True}), encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid acodex config"):
        load_config(config_path=extra)

    missing = tmp_path / "missing" / "config.json"
    assert load_config(config_path=missing).server.port == 45218


def test_config_read_os_error_and_empty_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no")),
    )
    with pytest.raises(ConfigError, match="Could not read"):
        load_config(config_path=path)

    assert ConfigMerger().deep_merge({"a": 1}, {"b": {}}) == {"a": 1}
