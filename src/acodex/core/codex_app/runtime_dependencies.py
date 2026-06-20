from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def is_descriptor_without_handler(result: dict[str, Any]) -> bool:
    if result.get("success") is not False:
        return False
    items = result.get("contentItems")
    if not isinstance(items, list):
        return False
    return any(
        isinstance(item, dict)
        and isinstance(item.get("text"), str)
        and "did not export a callable renderer handler" in item["text"]
        for item in items
    )


def load_workspace_dependencies_fallback() -> dict[str, Any]:
    runtime_root = _find_codex_runtime_root()
    if runtime_root is None:
        cache_root = Path.home() / ".cache" / "codex-runtimes"
        return {
            "success": False,
            "contentItems": [
                {
                    "type": "inputText",
                    "text": f"No Codex runtime with bundled dependencies was found under {cache_root}.",
                },
            ],
        }

    runtime_json = runtime_root / "runtime.json"
    runtime = json.loads(runtime_json.read_text())
    dependencies = runtime_root / "dependencies"
    node = dependencies / "node"
    python = dependencies / "python"
    node_executable = node / "bin" / "node"
    python_executable = python / "bin" / "python3"
    native_binaries = dependencies / "bin"

    text = "\n".join(
        [
            "Workspace dependencies are available for this local desktop thread.",
            "",
            "### Workspace Dependencies",
            "Use these bundled paths for sheets, slides, documents, PDFs, images, or browser automation:",
            f"- Bundle version: `{runtime.get('bundleVersion', 'unknown')}`",
            f"- Node.js executable: `{node_executable}`",
            f"- Node.js packages: `{node / 'node_modules'}`",
            f"- Python executable: `{python_executable}`",
            f"- Python packages: `{python}`",
            f"- Native binaries: `{native_binaries}`",
        ],
    )
    return {"success": True, "contentItems": [{"type": "inputText", "text": text}]}


def _find_codex_runtime_root() -> Path | None:
    cache_root = Path.home() / ".cache" / "codex-runtimes"
    if not cache_root.exists():
        return None

    candidates = sorted(
        (path.parent for path in cache_root.glob("*/runtime.json")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        dependencies = candidate / "dependencies"
        if (dependencies / "node").exists() and (dependencies / "python").exists():
            return candidate
    return None
