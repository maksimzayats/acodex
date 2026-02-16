from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from typing import Any

import pytest

from tools.vendor import latest_codex_release as release_tool


@dataclass
class _ReadableResponse:
    body: bytes

    def read(self) -> bytes:
        return self.body


def test_latest_stable_release_uses_pagination_and_skips_draft_and_prerelease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_github_get_json(*, url: str) -> object:
        calls.append(url)
        if url.endswith("page=1"):
            return [
                {
                    "id": 1,
                    "tag_name": "draft",
                    "published_at": "2026-01-01T00:00:00Z",
                    "html_url": "https://example.test/draft",
                    "draft": True,
                    "prerelease": False,
                },
                {
                    "id": 2,
                    "tag_name": "pre",
                    "published_at": "2026-01-02T00:00:00Z",
                    "html_url": "https://example.test/pre",
                    "draft": False,
                    "prerelease": True,
                },
            ]
        if url.endswith("page=2"):
            return [
                {
                    "id": 3,
                    "tag_name": "rust-v1.2.3",
                    "published_at": "2026-01-03T00:00:00Z",
                    "html_url": "https://example.test/stable",
                    "draft": False,
                    "prerelease": False,
                },
            ]
        return []

    monkeypatch.setattr(release_tool, "_github_get_json", fake_github_get_json)

    assert release_tool.latest_stable_release() == {
        "release_id": 3,
        "release_tag": "rust-v1.2.3",
        "release_published_at": "2026-01-03T00:00:00Z",
        "release_url": "https://example.test/stable",
    }
    assert len(calls) == 2
    assert "page=1" in calls[0]
    assert "page=2" in calls[1]


def test_latest_stable_release_raises_when_no_stable_release_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_github_get_json(*, url: str) -> object:
        if url.endswith("page=1"):
            return [
                {
                    "id": 1,
                    "tag_name": "draft",
                    "published_at": "2026-01-01T00:00:00Z",
                    "html_url": "https://example.test/draft",
                    "draft": True,
                    "prerelease": False,
                },
            ]
        return []

    monkeypatch.setattr(release_tool, "_github_get_json", fake_github_get_json)

    with pytest.raises(release_tool._GitHubApiError) as exc_info:
        release_tool.latest_stable_release()

    assert "No stable GitHub Releases found" in str(exc_info.value)


def test_type_validation_helpers_raise_on_wrong_input_types() -> None:
    with pytest.raises(release_tool._GitHubApiError) as exc_info:
        release_tool._require_dict([], context="ctx")
    assert "Expected object" in str(exc_info.value)

    with pytest.raises(release_tool._GitHubApiError) as exc_info:
        release_tool._require_list({}, context="ctx")
    assert "Expected array" in str(exc_info.value)

    with pytest.raises(release_tool._GitHubApiError) as exc_info:
        release_tool._require_str({}, "tag_name", context="ctx")
    assert "Missing/invalid" in str(exc_info.value)

    with pytest.raises(release_tool._GitHubApiError) as exc_info:
        release_tool._require_int({"id": 0}, "id", context="ctx")
    assert "Missing/invalid" in str(exc_info.value)

    with pytest.raises(release_tool._GitHubApiError) as exc_info:
        release_tool._require_bool({"draft": "yes"}, "draft", context="ctx")
    assert "Missing/invalid" in str(exc_info.value)


def test_main_with_field_prints_plain_value(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(
        release_tool,
        "latest_stable_release",
        lambda: {
            "release_id": 10,
            "release_tag": "rust-v9.9.9",
            "release_published_at": "2026-01-10T00:00:00Z",
            "release_url": "https://example.test/release",
        },
    )

    assert release_tool.main(["--field", "release_tag"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "rust-v9.9.9\n"


def test_main_without_field_prints_json(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(
        release_tool,
        "latest_stable_release",
        lambda: {
            "release_id": 10,
            "release_tag": "rust-v9.9.9",
            "release_published_at": "2026-01-10T00:00:00Z",
            "release_url": "https://example.test/release",
        },
    )

    assert release_tool.main([]) == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)

    assert set(parsed) == {
        "release_id",
        "release_tag",
        "release_published_at",
        "release_url",
    }
    assert captured.out.endswith("\n")


@pytest.mark.parametrize(
    ("token", "expected_authorization"),
    [
        (None, None),
        ("my-token", "Bearer my-token"),
    ],
)
def test_github_get_json_headers_include_accept_and_user_agent_and_optional_auth(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token: str | None,
    expected_authorization: str | None,
) -> None:
    captured_request: dict[str, Any] = {}

    def fake_urlopen(request: Any, *, timeout: int) -> contextlib.AbstractContextManager[Any]:
        captured_request["request"] = request
        captured_request["timeout"] = timeout
        return contextlib.nullcontext(_ReadableResponse(body=b'{"ok": true}'))

    monkeypatch.setattr("tools.vendor.latest_codex_release.urllib.request.urlopen", fake_urlopen)
    if token is None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    else:
        monkeypatch.setenv("GITHUB_TOKEN", token)

    assert release_tool._github_get_json(url="https://api.github.test/example") == {"ok": True}

    request = captured_request["request"]
    headers = {key.lower(): value for key, value in request.header_items()}
    assert captured_request["timeout"] == 30
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["user-agent"] == release_tool._USER_AGENT
    if expected_authorization is None:
        assert "authorization" not in headers
    else:
        assert headers["authorization"] == expected_authorization
