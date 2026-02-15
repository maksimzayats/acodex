from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess  # noqa: S404
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from operator import itemgetter
from pathlib import Path
from typing import Final

_REPO_URL: Final[str] = "https://github.com/openai/codex"
_REPO_GIT_URL: Final[str] = "https://github.com/openai/codex.git"
_REPO_SLUG: Final[str] = "openai/codex"
_UPSTREAM_PATH: Final[str] = "sdk/typescript"
_API_ROOT: Final[str] = "https://api.github.com"
_USER_AGENT: Final[str] = "acodex-vendor-bot"
_HTTP_NOT_FOUND: Final[int] = 404
_GIT_SHA_LEN: Final[int] = 40


class _VendorError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _vendor_root() -> Path:
    return _repo_root() / "vendor" / "codex-ts-sdk"


def _upstream_json_path() -> Path:
    return _vendor_root() / "UPSTREAM.json"


def _github_get_json(*, url: str) -> object:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
    }

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == _HTTP_NOT_FOUND:
            raise _VendorError(f"Tag is not an official GitHub Release: {url}") from exc
        raise _VendorError(f"GitHub API error: {exc.code} {exc.reason} for {url}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover
        raise _VendorError(f"GitHub API request failed for {url}: {exc.reason}") from exc

    data: object = json.loads(body)
    return data


def _require_dict(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _VendorError(f"Expected object for {context}, got {type(value).__name__}")
    return value


def _require_str(obj: dict[str, object], key: str, *, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise _VendorError(f"Missing/invalid {context}.{key}")
    return value


def _require_int(obj: dict[str, object], key: str, *, context: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or value <= 0:
        raise _VendorError(f"Missing/invalid {context}.{key}")
    return value


def _require_bool(obj: dict[str, object], key: str, *, context: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise _VendorError(f"Missing/invalid {context}.{key}")
    return value


def _git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise _VendorError("git not found on PATH.")
    return git


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [_git_executable(), *args],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )


def _git_check_object(*, repo_dir: Path, revspec: str) -> bool:
    proc = _run_git("cat-file", "-e", revspec, cwd=repo_dir)
    return proc.returncode == 0


def _git_show_bytes(*, repo_dir: Path, revspec: str) -> bytes:
    proc = subprocess.run(  # noqa: S603
        [_git_executable(), "-C", str(repo_dir), "show", revspec],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise _VendorError(f"git show failed for {revspec}: {stderr.strip()}")
    return proc.stdout


def _git_rev_parse_head(*, repo_dir: Path) -> str:
    proc = _run_git("rev-parse", "HEAD", cwd=repo_dir)
    if proc.returncode != 0:
        raise _VendorError(f"git rev-parse HEAD failed: {proc.stderr.strip()}")
    sha = proc.stdout.strip()
    if len(sha) != _GIT_SHA_LEN or any(ch not in "0123456789abcdef" for ch in sha):
        raise _VendorError(f"Unexpected HEAD sha: {sha!r}")
    return sha


def _replace_tree(*, src_dir: Path, dst_dir: Path) -> None:
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dst_dir)


def _tree_hash(*, root_dir: Path) -> str:
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


def _read_existing_tag() -> str:
    path = _upstream_json_path()
    if not path.exists():
        raise _VendorError("Missing vendor/codex-ts-sdk/UPSTREAM.json; pass --tag explicitly.")

    data: object = json.loads(path.read_text(encoding="utf-8"))
    obj = _require_dict(data, context="UPSTREAM.json")
    tag = obj.get("release_tag")
    if not isinstance(tag, str) or not tag:
        raise _VendorError("UPSTREAM.json missing/invalid release_tag.")
    return tag


def _resolve_release(*, tag: str) -> dict[str, object]:
    url_tag = urllib.parse.quote(tag, safe="")
    url = f"{_API_ROOT}/repos/{_REPO_SLUG}/releases/tags/{url_tag}"
    payload = _github_get_json(url=url)
    release = _require_dict(payload, context="release")

    if _require_bool(release, "draft", context="release"):
        raise _VendorError(f"Tag is a draft release (unsupported): {tag}")
    if _require_bool(release, "prerelease", context="release"):
        raise _VendorError(f"Tag is a prerelease (unsupported): {tag}")

    return {
        "release_id": _require_int(release, "id", context="release"),
        "release_tag": _require_str(release, "tag_name", context="release"),
        "release_published_at": _require_str(release, "published_at", context="release"),
        "release_url": _require_str(release, "html_url", context="release"),
    }


def _clone_sparse_checkout(*, tag: str, tmp_dir: Path) -> Path:
    repo_dir = tmp_dir / "codex"
    proc = subprocess.run(  # noqa: S603
        [
            _git_executable(),
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "--branch",
            tag,
            _REPO_GIT_URL,
            str(repo_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise _VendorError(f"git clone failed: {proc.stderr.strip()}")

    proc = _run_git("sparse-checkout", "set", _UPSTREAM_PATH, cwd=repo_dir)
    if proc.returncode != 0:
        raise _VendorError(f"git sparse-checkout failed: {proc.stderr.strip()}")

    return repo_dir


def _write_root_file_if_present(*, repo_dir: Path, tag: str, name: str, dst_dir: Path) -> None:
    revspec = f"{tag}:{name}"
    if not _git_check_object(repo_dir=repo_dir, revspec=revspec):
        return
    (dst_dir / name).write_bytes(_git_show_bytes(repo_dir=repo_dir, revspec=revspec))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Vendor the Codex TypeScript SDK (sdk/typescript) from an official GitHub Release."
        ),
    )
    parser.add_argument(
        "--tag",
        help=(
            "Upstream release tag to vendor (must exist as a stable GitHub Release). "
            "If omitted, read release_tag from vendor/codex-ts-sdk/UPSTREAM.json."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    tag: str = args.tag or _read_existing_tag()

    release_info = _resolve_release(tag=tag)
    canonical_tag = release_info["release_tag"]
    if not isinstance(canonical_tag, str):
        raise _VendorError("Internal error: release_tag must be a string.")

    with tempfile.TemporaryDirectory(prefix="acodex-vendor-") as tmp:
        repo_dir = _clone_sparse_checkout(tag=canonical_tag, tmp_dir=Path(tmp))
        upstream_dir = repo_dir / _UPSTREAM_PATH
        if not upstream_dir.is_dir():
            raise _VendorError(f"Upstream path missing in {canonical_tag}: {_UPSTREAM_PATH}")

        vendor_dir = _vendor_root()
        _replace_tree(src_dir=upstream_dir, dst_dir=vendor_dir)

        _write_root_file_if_present(
            repo_dir=repo_dir,
            tag=canonical_tag,
            name="LICENSE",
            dst_dir=vendor_dir,
        )
        _write_root_file_if_present(
            repo_dir=repo_dir,
            tag=canonical_tag,
            name="NOTICE",
            dst_dir=vendor_dir,
        )

        commit = _git_rev_parse_head(repo_dir=repo_dir)
        tree_hash = _tree_hash(root_dir=vendor_dir)

    upstream_json = {
        "repo": _REPO_URL,
        "path": _UPSTREAM_PATH,
        "release_id": release_info["release_id"],
        "release_tag": canonical_tag,
        "release_published_at": release_info["release_published_at"],
        "release_url": release_info["release_url"],
        "commit": commit,
        "tree_hash": tree_hash,
    }

    _upstream_json_path().write_text(
        json.dumps(upstream_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    sys.stdout.write(f"Vendored {_UPSTREAM_PATH} at {canonical_tag} into vendor/codex-ts-sdk/\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except _VendorError as exc:
        sys.stderr.write(f"error: {exc}\n")
        raise SystemExit(1) from exc
