from __future__ import annotations

import pytest

from acodex import CodexAppCdpClient, CodexAppCdpSettings


def test_settings_read_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACODEX_CDP_ENDPOINT", "http://127.0.0.1:9333")
    monkeypatch.setenv("ACODEX_CDP_TARGET_URL", "app://custom/index.html")
    monkeypatch.setenv("ACODEX_CDP_TARGET_URL_PREFIX", "app://custom/")
    monkeypatch.setenv("ACODEX_CDP_HTTP_TIMEOUT", "1.25")
    monkeypatch.setenv("ACODEX_CDP_RUNTIME_TIMEOUT", "2.5")

    settings = CodexAppCdpSettings()

    assert settings.endpoint == "http://127.0.0.1:9333"
    assert settings.target_url == "app://custom/index.html"
    assert settings.target_url_prefix == "app://custom/"
    assert settings.http_timeout == pytest.approx(1.25)
    assert settings.runtime_timeout == pytest.approx(2.5)


def test_client_explicit_endpoint_overrides_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACODEX_CDP_ENDPOINT", "http://env:9222")

    client = CodexAppCdpClient(endpoint="http://explicit:9222")

    assert client.settings.endpoint == "http://explicit:9222"
