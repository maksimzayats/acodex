from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Final

_REPO: Final[str] = "openai/codex"
_API_ROOT: Final[str] = "https://api.github.com"
_USER_AGENT: Final[str] = "acodex-vendor-bot"


class _GitHubApiError(RuntimeError):
    pass


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
    except urllib.error.HTTPError as exc:  # pragma: no cover
        raise _GitHubApiError(f"GitHub API error: {exc.code} {exc.reason} for {url}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover
        raise _GitHubApiError(f"GitHub API request failed for {url}: {exc.reason}") from exc

    data: object = json.loads(body)
    return data


def _require_dict(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _GitHubApiError(f"Expected object for {context}, got {type(value).__name__}")
    return value


def _require_list(value: object, *, context: str) -> list[object]:
    if not isinstance(value, list):
        raise _GitHubApiError(f"Expected array for {context}, got {type(value).__name__}")
    return value


def _require_str(obj: dict[str, object], key: str, *, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise _GitHubApiError(f"Missing/invalid {context}.{key}")
    return value


def _require_int(obj: dict[str, object], key: str, *, context: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or value <= 0:
        raise _GitHubApiError(f"Missing/invalid {context}.{key}")
    return value


def _require_bool(obj: dict[str, object], key: str, *, context: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise _GitHubApiError(f"Missing/invalid {context}.{key}")
    return value


def latest_stable_release() -> dict[str, object]:
    page = 1
    while True:
        url = f"{_API_ROOT}/repos/{_REPO}/releases?per_page=100&page={page}"
        payload = _github_get_json(url=url)
        releases = _require_list(payload, context="releases")
        if not releases:
            break

        for idx, raw_release in enumerate(releases):
            context = f"releases[{page}:{idx}]"
            release = _require_dict(raw_release, context=context)
            if _require_bool(release, "draft", context=context):
                continue
            if _require_bool(release, "prerelease", context=context):
                continue

            return {
                "release_id": _require_int(release, "id", context=context),
                "release_tag": _require_str(release, "tag_name", context=context),
                "release_published_at": _require_str(release, "published_at", context=context),
                "release_url": _require_str(release, "html_url", context=context),
            }

        page += 1

    raise _GitHubApiError("No stable GitHub Releases found for openai/codex.")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the latest stable GitHub Release for openai/codex.",
    )
    parser.add_argument(
        "--field",
        choices=("release_id", "release_tag", "release_published_at", "release_url"),
        help="Print only a single field (plain text).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    info = latest_stable_release()

    field: str | None = args.field
    if field is not None:
        value = info[field]
        sys.stdout.write(f"{value}\n")
        return 0

    sys.stdout.write(json.dumps(info, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
