from __future__ import annotations

RENDERER_ASSET_DISCOVERY_EXPRESSION = r"""
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
