from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

# Ensure the local package is importable for autodoc without requiring an install step.
_DOCS_DIR = Path(__file__).resolve().parent
_ROOT = _DOCS_DIR.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_DOCS_DIR / "_extensions"))

project = "acodex"
author = "Maksim Zayats"


def _normalize_display_version(raw_release: str) -> str:
    stable_release = raw_release
    for marker in ("+", ".post", ".dev"):
        stable_release = stable_release.split(marker, maxsplit=1)[0]
    return stable_release


def _resolve_metadata_release(package_name: str = "acodex") -> str:
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return "0+unknown"


def _read_latest_tag(repo_root: Path) -> str | None:
    git_binary = shutil.which("git")
    if git_binary is None:
        return None

    try:
        completed = subprocess.run(  # noqa: S603
            [git_binary, "describe", "--tags", "--abbrev=0"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    latest_tag = completed.stdout.strip()
    if not latest_tag:
        return None
    return latest_tag.removeprefix("v")


def _resolve_docs_versions(
    metadata_release: str,
    repo_root: Path,
    git_tag_reader: Callable[[Path], str | None] = _read_latest_tag,
) -> tuple[str, str]:
    release = metadata_release
    if metadata_release.startswith("0.0.0"):
        latest_tag = git_tag_reader(repo_root)
        release = latest_tag.removeprefix("v") if latest_tag else ""
    version = _normalize_display_version(release)
    return release, version


release, version = _resolve_docs_versions(_resolve_metadata_release(), _ROOT)

extensions: list[str] = [
    # Built-in Sphinx extensions
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
]

root_doc = "index"
source_suffix: dict[str, str] = {
    ".rst": "restructuredtext",
}

exclude_patterns: list[str] = ["_build"]

html_theme = "furo"
html_static_path: list[str] = ["_static"]
html_css_files: list[str] = ["custom.css"]
templates_path: list[str] = ["_templates"]
html_theme_options = {
    "source_repository": "https://github.com/maksimzayats/acodex",
    "source_branch": (
        os.environ.get("ACODEX_DOCS_SOURCE_BRANCH") or os.environ.get("GITHUB_REF_NAME") or "main"
    ).strip(),
    "source_directory": "docs",
    "top_of_page_buttons": ["view", "edit"],
}

# ---- Quality of life / navigation -------------------------------------------------

autosummary_generate = False
autodoc_typehints = "none"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# ---- SEO-ish defaults -------------------------------------------------------------

html_title = "acodex: Python SDK for the Codex CLI"

# If you set a base URL, we'll emit a sitemap and robots.txt (see docs/_extensions/acodex_sitemap.py).
# Default to the canonical docs domain, but allow contributors to disable by setting ACODEX_DOCS_BASEURL="".
html_baseurl = os.environ.get("ACODEX_DOCS_BASEURL", "https://docs.acodex.dev").strip()
if html_baseurl:
    extensions.append("acodex_sitemap")

html_meta = {
    "description": (
        "acodex is a typed Python SDK that wraps the `codex` CLI, providing sync and async clients "
        "to run agent threads, stream JSONL events, and consume structured items."
    ),
    "keywords": ("codex, codex cli, sdk, python, agent, threads, streaming, jsonl, tools"),
}

# Pyodide runner configuration
pyodide_runner_packages: list[str] = ["acodex"]
