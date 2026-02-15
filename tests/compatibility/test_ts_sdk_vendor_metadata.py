from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from operator import itemgetter
from pathlib import Path

from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_ROOT


def _compute_tree_hash(*, root_dir: Path) -> str:
    upstream_json = root_dir / "UPSTREAM.json"
    hasher = hashlib.sha256()

    entries: list[tuple[str, Path]] = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            path = Path(dirpath) / filename
            if not path.is_file():
                continue
            if path == upstream_json:
                continue
            rel_posix = path.relative_to(root_dir).as_posix()
            entries.append((rel_posix, path))

    entries.sort(key=itemgetter(0))

    for rel_posix, path in entries:
        hasher.update(rel_posix.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())

    return f"sha256:{hasher.hexdigest()}"


def _parse_github_iso8601(value: str) -> datetime:
    # GitHub typically returns timestamps like "2026-02-12T20:05:52Z".
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def test_vendor_metadata_file_exists_and_is_valid() -> None:
    upstream_path = VENDOR_TS_SDK_ROOT / "UPSTREAM.json"
    assert upstream_path.exists(), "Missing vendor/codex-ts-sdk/UPSTREAM.json"

    data = json.loads(upstream_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "UPSTREAM.json must be a JSON object"

    assert data.get("repo") == "https://github.com/openai/codex"
    assert data.get("path") == "sdk/typescript"

    release_tag = data.get("release_tag")
    assert isinstance(release_tag, str)
    assert re.match(r"^rust-v\d+\.\d+\.\d+$", release_tag)

    release_id = data.get("release_id")
    assert isinstance(release_id, int)
    assert release_id > 0

    release_published_at = data.get("release_published_at")
    assert isinstance(release_published_at, str)
    assert release_published_at
    _parse_github_iso8601(release_published_at)

    release_url = data.get("release_url")
    assert isinstance(release_url, str)
    assert release_url

    commit = data.get("commit")
    assert isinstance(commit, str)
    assert re.match(r"^[0-9a-f]{40}$", commit)

    tree_hash = data.get("tree_hash")
    assert isinstance(tree_hash, str)
    assert re.match(r"^sha256:[0-9a-f]{64}$", tree_hash)
    assert tree_hash == _compute_tree_hash(root_dir=VENDOR_TS_SDK_ROOT)


def test_vendor_required_files_exist() -> None:
    required_paths = (
        VENDOR_TS_SDK_ROOT / "package.json",
        VENDOR_TS_SDK_ROOT / "src" / "items.ts",
        VENDOR_TS_SDK_ROOT / "src" / "events.ts",
        VENDOR_TS_SDK_ROOT / "src" / "index.ts",
    )
    for path in required_paths:
        assert path.exists(), f"Missing required vendored file: {path}"


def test_package_json_points_at_upstream_repo_and_directory() -> None:
    package_json_path = VENDOR_TS_SDK_ROOT / "package.json"
    data = json.loads(package_json_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "vendor/codex-ts-sdk/package.json must be a JSON object"

    repository = data.get("repository")
    assert isinstance(repository, dict), "package.json repository must be an object"

    url = repository.get("url")
    assert isinstance(url, str)
    assert "openai/codex" in url

    directory = repository.get("directory")
    assert directory == "sdk/typescript"
