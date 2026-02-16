from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tools.vendor import fetch_codex_ts_sdk as vendor_tool


@dataclass
class _ReadableResponse:
    body: bytes

    def read(self) -> bytes:
        return self.body


@dataclass
class _FakeGitResult:
    returncode: int
    stdout: str | bytes
    stderr: str | bytes


def test_tree_hash_ignores_upstream_json(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    (root / "src").mkdir(parents=True)
    (root / "src" / "file.txt").write_text("alpha", encoding="utf-8")

    initial_hash = vendor_tool._tree_hash(root_dir=root)

    (root / "UPSTREAM.json").write_text('{"release_tag":"rust-v1"}', encoding="utf-8")
    with_upstream_hash = vendor_tool._tree_hash(root_dir=root)
    assert with_upstream_hash == initial_hash

    (root / "UPSTREAM.json").write_text('{"release_tag":"rust-v2"}', encoding="utf-8")
    changed_upstream_hash = vendor_tool._tree_hash(root_dir=root)
    assert changed_upstream_hash == initial_hash

    (root / "src" / "file.txt").write_text("beta", encoding="utf-8")
    changed_source_hash = vendor_tool._tree_hash(root_dir=root)
    assert changed_source_hash != initial_hash


def test_replace_tree_replaces_existing_destination_directory(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "new.txt").write_text("new", encoding="utf-8")
    (dst / "old.txt").write_text("old", encoding="utf-8")

    vendor_tool._replace_tree(src_dir=src, dst_dir=dst)

    assert (dst / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (dst / "old.txt").exists()


def test_read_existing_tag_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    upstream_json = tmp_path / "UPSTREAM.json"
    upstream_json.write_text('{"release_tag":"rust-v1.2.3"}', encoding="utf-8")
    monkeypatch.setattr(vendor_tool, "_upstream_json_path", lambda: upstream_json)

    assert vendor_tool._read_existing_tag() == "rust-v1.2.3"


def test_read_existing_tag_missing_file_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upstream_json = tmp_path / "UPSTREAM.json"
    monkeypatch.setattr(vendor_tool, "_upstream_json_path", lambda: upstream_json)

    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._read_existing_tag()

    assert "Missing vendor/codex-ts-sdk/UPSTREAM.json" in str(exc_info.value)


def test_read_existing_tag_invalid_data_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upstream_json = tmp_path / "UPSTREAM.json"
    upstream_json.write_text('{"release_tag":""}', encoding="utf-8")
    monkeypatch.setattr(vendor_tool, "_upstream_json_path", lambda: upstream_json)

    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._read_existing_tag()

    assert "UPSTREAM.json missing/invalid release_tag" in str(exc_info.value)


def test_git_rev_parse_head_validates_sha_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    valid_sha = "a" * 40

    def fake_run_git(*args: str, cwd: Path) -> _FakeGitResult:
        return _FakeGitResult(returncode=0, stdout=f"{valid_sha}\n", stderr="")

    monkeypatch.setattr(vendor_tool, "_run_git", fake_run_git)
    assert vendor_tool._git_rev_parse_head(repo_dir=tmp_path) == valid_sha

    def fake_run_git_invalid(*args: str, cwd: Path) -> _FakeGitResult:
        return _FakeGitResult(returncode=0, stdout="INVALID_SHA\n", stderr="")

    monkeypatch.setattr(vendor_tool, "_run_git", fake_run_git_invalid)
    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._git_rev_parse_head(repo_dir=tmp_path)

    assert "Unexpected HEAD sha" in str(exc_info.value)


def test_git_show_bytes_raises_with_stderr_on_nonzero_returncode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(vendor_tool, "_git_executable", lambda: "git")

    def fake_subprocess_run(*args: object, **kwargs: object) -> _FakeGitResult:
        return _FakeGitResult(returncode=1, stdout=b"", stderr=b"fatal: bad revision")

    monkeypatch.setattr("tools.vendor.fetch_codex_ts_sdk.subprocess.run", fake_subprocess_run)

    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._git_show_bytes(repo_dir=tmp_path, revspec="HEAD:LICENSE")

    assert "git show failed" in str(exc_info.value)
    assert "fatal: bad revision" in str(exc_info.value)


def test_resolve_release_rejects_draft_and_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_github_get_json_draft(*, url: str) -> object:
        return {
            "id": 1,
            "tag_name": "rust-v1",
            "published_at": "2026-01-01T00:00:00Z",
            "html_url": "https://example.test/release",
            "draft": True,
            "prerelease": False,
        }

    monkeypatch.setattr(vendor_tool, "_github_get_json", fake_github_get_json_draft)
    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._resolve_release(tag="rust-v1")
    assert "draft release" in str(exc_info.value)

    def fake_github_get_json_prerelease(*, url: str) -> object:
        return {
            "id": 1,
            "tag_name": "rust-v1",
            "published_at": "2026-01-01T00:00:00Z",
            "html_url": "https://example.test/release",
            "draft": False,
            "prerelease": True,
        }

    monkeypatch.setattr(vendor_tool, "_github_get_json", fake_github_get_json_prerelease)
    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._resolve_release(tag="rust-v1")
    assert "prerelease" in str(exc_info.value)


def test_resolve_release_returns_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_github_get_json(*, url: str) -> object:
        return {
            "id": 99,
            "tag_name": "rust-v9.9.9",
            "published_at": "2026-02-01T00:00:00Z",
            "html_url": "https://example.test/rust-v9.9.9",
            "draft": False,
            "prerelease": False,
        }

    monkeypatch.setattr(vendor_tool, "_github_get_json", fake_github_get_json)

    assert vendor_tool._resolve_release(tag="rust-v9.9.9") == {
        "release_id": 99,
        "release_tag": "rust-v9.9.9",
        "release_published_at": "2026-02-01T00:00:00Z",
        "release_url": "https://example.test/rust-v9.9.9",
    }


def test_git_executable_raises_when_git_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.vendor.fetch_codex_ts_sdk.shutil.which", lambda _: None)

    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._git_executable()

    assert "git not found on PATH" in str(exc_info.value)


def test_github_get_json_maps_http_404_to_release_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeHttpError(Exception):
        def __init__(self, code: int, reason: str) -> None:
            self.code = code
            self.reason = reason

    monkeypatch.setattr("tools.vendor.fetch_codex_ts_sdk.urllib.error.HTTPError", _FakeHttpError)

    def fake_urlopen(
        request: Any,
        *,
        timeout: int,
    ) -> contextlib.AbstractContextManager[_ReadableResponse]:
        raise _FakeHttpError(code=404, reason="Not Found")

    monkeypatch.setattr("tools.vendor.fetch_codex_ts_sdk.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool._github_get_json(
            url="https://api.github.test/repos/openai/codex/releases/tags/x",
        )

    assert "not an official GitHub Release" in str(exc_info.value)


def test_main_success_path_writes_upstream_json_and_prints_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(vendor_tool, "_repo_root", lambda: repo_root)

    def fake_resolve_release(*, tag: str) -> dict[str, object]:
        return {
            "release_id": 11,
            "release_tag": "rust-v1.2.3",
            "release_published_at": "2026-01-11T00:00:00Z",
            "release_url": "https://example.test/rust-v1.2.3",
        }

    monkeypatch.setattr(vendor_tool, "_resolve_release", fake_resolve_release)

    def fake_clone_sparse_checkout(*, tag: str, tmp_dir: Path) -> Path:
        repo_dir = tmp_dir / "codex"
        upstream_dir = repo_dir / "sdk" / "typescript"
        upstream_dir.mkdir(parents=True)
        (upstream_dir / "index.ts").write_text("export {};\n", encoding="utf-8")
        return repo_dir

    def fake_write_root_file_if_present(
        *,
        repo_dir: Path,
        tag: str,
        name: str,
        dst_dir: Path,
    ) -> None:
        return None

    def fake_git_rev_parse_head(*, repo_dir: Path) -> str:
        return "a" * 40

    def fake_tree_hash(*, root_dir: Path) -> str:
        return "sha256:" + ("b" * 64)

    monkeypatch.setattr(vendor_tool, "_clone_sparse_checkout", fake_clone_sparse_checkout)
    monkeypatch.setattr(vendor_tool, "_write_root_file_if_present", fake_write_root_file_if_present)
    monkeypatch.setattr(vendor_tool, "_git_rev_parse_head", fake_git_rev_parse_head)
    monkeypatch.setattr(vendor_tool, "_tree_hash", fake_tree_hash)

    assert vendor_tool.main(["--tag", "rust-v1.2.3"]) == 0
    captured = capsys.readouterr()

    vendor_dir = repo_root / "vendor" / "codex-ts-sdk"
    upstream_json_path = vendor_dir / "UPSTREAM.json"
    assert (vendor_dir / "index.ts").exists()
    upstream_data = json.loads(upstream_json_path.read_text(encoding="utf-8"))

    assert upstream_data == {
        "repo": "https://github.com/openai/codex",
        "path": "sdk/typescript",
        "release_id": 11,
        "release_tag": "rust-v1.2.3",
        "release_published_at": "2026-01-11T00:00:00Z",
        "release_url": "https://example.test/rust-v1.2.3",
        "commit": "a" * 40,
        "tree_hash": "sha256:" + ("b" * 64),
    }
    assert "Vendored sdk/typescript at rust-v1.2.3" in captured.out


def test_main_raises_when_upstream_path_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(vendor_tool, "_repo_root", lambda: repo_root)

    def fake_resolve_release(*, tag: str) -> dict[str, object]:
        return {
            "release_id": 11,
            "release_tag": "rust-v1.2.3",
            "release_published_at": "2026-01-11T00:00:00Z",
            "release_url": "https://example.test/rust-v1.2.3",
        }

    monkeypatch.setattr(vendor_tool, "_resolve_release", fake_resolve_release)

    def fake_clone_sparse_checkout(*, tag: str, tmp_dir: Path) -> Path:
        repo_dir = tmp_dir / "codex"
        repo_dir.mkdir(parents=True)
        return repo_dir

    monkeypatch.setattr(vendor_tool, "_clone_sparse_checkout", fake_clone_sparse_checkout)

    with pytest.raises(vendor_tool._VendorError) as exc_info:
        vendor_tool.main(["--tag", "rust-v1.2.3"])

    assert "Upstream path missing" in str(exc_info.value)
