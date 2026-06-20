from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from acodex.core.codex_app.cdp import CodexCDPClient, CodexCDPError


@dataclass(frozen=True, slots=True)
class CodexRendererAssets:
    app_scope_url: str
    dynamic_tools_url: str
    manager_url: str
    vscode_api_url: str | None

    def as_payload(self) -> dict[str, str | None]:
        """Return the asset names expected by the renderer bridge script.

        Returns:
            A renderer bridge asset payload.

        """
        return {
            "appScopeUrl": self.app_scope_url,
            "dynamicToolsUrl": self.dynamic_tools_url,
            "managerUrl": self.manager_url,
            "vscodeApiUrl": self.vscode_api_url,
        }


class CodexRendererAssetDiscoveryError(RuntimeError):
    """Raised when required Codex renderer bundles cannot be discovered."""


async def discover_renderer_assets(cdp: CodexCDPClient) -> CodexRendererAssets:
    """Find the renderer bundles needed to list and call Codex app tools.

    Returns:
        The discovered Codex renderer asset URLs.

    Raises:
        CodexRendererAssetDiscoveryError: If required renderer assets cannot be found.

    """
    tree = await cdp.resource_tree()
    frame_tree = tree.get("frameTree")
    if not isinstance(frame_tree, dict):
        raise CodexRendererAssetDiscoveryError("CDP Page.getResourceTree returned no frame tree")

    matches: dict[str, str] = {}
    for frame_id, url in _collect_javascript_resources(frame_tree):
        if not url.startswith("app://-"):
            continue

        try:
            content = await cdp.resource_content(frame_id, url)
        except CodexCDPError:
            continue

        _record_asset_matches(matches, content=content, url=url)

    missing = _missing_required_assets(matches)
    if missing:
        matches.update(await _discover_assets_in_renderer(cdp))
        missing = _missing_required_assets(matches)
        if missing:
            raise CodexRendererAssetDiscoveryError(
                "Could not discover required Codex renderer assets: "
                + ", ".join(missing)
                + ". Make sure the Codex app window is open and the current thread has loaded.",
            )

    return CodexRendererAssets(
        app_scope_url=matches["app_scope"],
        dynamic_tools_url=matches["dynamic_tools"],
        manager_url=matches["manager"],
        vscode_api_url=matches.get("vscode_api"),
    )


def _record_asset_matches(matches: dict[str, str], *, content: str, url: str) -> None:
    if "vscode://codex/" in content and "sendMessageFromView" in content:
        matches.setdefault("vscode_api", url)
    if "codex_app" in content and "list_threads" in content and "send_message_to_thread" in content:
        matches.setdefault("dynamic_tools", url)
    if "read_thread_terminal" in content and "load_workspace_dependencies" in content:
        matches.setdefault("manager", url)
    if (
        "queryClient" in content
        and "familyBindings" in content
        and ("__scopeBrand" in content or "Missing query client" in content)
    ):
        matches.setdefault("app_scope", url)


def _missing_required_assets(matches: dict[str, str]) -> list[str]:
    return [name for name in ("app_scope", "dynamic_tools", "manager") if name not in matches]


async def _discover_assets_in_renderer(cdp: CodexCDPClient) -> dict[str, str]:
    expression = r"""
(async () => {
  const matches = {};
  const urls = new Set();
  for (const entry of performance.getEntriesByType("resource")) {
    if (typeof entry.name === "string" && entry.name.includes(".js")) {
      urls.add(entry.name);
    }
  }
  for (const script of document.querySelectorAll("script[src]")) {
    urls.add(script.src);
  }
  const queue = Array.from(urls);
  const seen = new Set();
  for (let index = 0; index < queue.length && index < 1000; index += 1) {
    const url = queue[index];
    if (seen.has(url)) continue;
    seen.add(url);
    if (!url.startsWith("app://-")) continue;
    let content = "";
    try {
      const response = await fetch(url);
      content = await response.text();
    } catch {
      continue;
    }
    if (!matches.vscode_api && content.includes("vscode://codex/") && content.includes("sendMessageFromView")) {
      matches.vscode_api = url;
    }
    if (!matches.dynamic_tools && content.includes("codex_app") && content.includes("list_threads") && content.includes("send_message_to_thread")) {
      matches.dynamic_tools = url;
    }
    if (!matches.manager && content.includes("read_thread_terminal") && content.includes("load_workspace_dependencies")) {
      matches.manager = url;
    }
    if (!matches.app_scope && content.includes("queryClient") && content.includes("familyBindings") && (content.includes("__scopeBrand") || content.includes("Missing query client"))) {
      matches.app_scope = url;
    }
    for (const match of content.matchAll(/[\"'`](\.\/[^\"'`]+\.js)[\"'`]/g)) {
      try {
        const childUrl = new URL(match[1], url).href;
        if (!seen.has(childUrl)) queue.push(childUrl);
      } catch {
        // Ignore malformed bundle references.
      }
    }
    if (matches.app_scope && matches.dynamic_tools && matches.manager && matches.vscode_api) {
      break;
    }
  }
  return JSON.stringify(matches);
})()
"""
    result = await cdp.evaluate(expression, await_promise=True)
    if isinstance(result, str):
        parsed = json.loads(result)
        return _string_dict(parsed)
    return _string_dict(result)


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, str)}


def _collect_javascript_resources(frame_tree: dict[str, Any]) -> list[tuple[str, str]]:
    resources: list[tuple[str, str]] = []

    def visit(node: dict[str, Any]) -> None:
        frame = node.get("frame", {})
        frame_id = frame.get("id") if isinstance(frame, dict) else None
        if isinstance(frame_id, str):
            for resource in node.get("resources", []) or []:
                if not isinstance(resource, dict):
                    continue
                url = resource.get("url")
                mime_type = resource.get("mimeType", "")
                resource_type = resource.get("type", "")
                if isinstance(url, str) and (
                    url.endswith(".js")
                    or resource_type == "Script"
                    or "javascript" in str(mime_type)
                ):
                    resources.append((frame_id, url))
        for child in node.get("childFrames", []) or []:
            if isinstance(child, dict):
                visit(child)

    visit(frame_tree)
    return resources
