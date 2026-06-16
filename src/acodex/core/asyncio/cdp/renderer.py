from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from acodex.core.asyncio.cdp.errors import CodexAppCdpDiscoveryError
from acodex.core.asyncio.cdp.json_utils import dump_json
from acodex.core.asyncio.cdp.types import CodexAppToolDiscovery, JsonObject, JsonValue

_DISCOVERY_GLOBAL_KEY: Final = "__acodexCdpBackendV2"

READ_ONLY_CODEX_APP_THREAD_TOOL_NAMES: Final = ("list_threads", "read_thread")
MUTATING_CODEX_APP_THREAD_TOOL_NAMES: Final = (
    "create_thread",
    "fork_thread",
    "send_message_to_thread",
    "set_thread_pinned",
    "set_thread_archived",
    "set_thread_title",
    "handoff_thread",
)
ALL_CODEX_APP_THREAD_TOOL_NAMES: Final = (
    *READ_ONLY_CODEX_APP_THREAD_TOOL_NAMES,
    *MUTATING_CODEX_APP_THREAD_TOOL_NAMES,
)


def build_tool_discovery_expression(
    *,
    tool_names: Sequence[str] = ALL_CODEX_APP_THREAD_TOOL_NAMES,
    required_tool_names: Sequence[str] = READ_ONLY_CODEX_APP_THREAD_TOOL_NAMES,
) -> str:
    tool_names_json = dump_json(list(tool_names))
    required_tool_names_json = dump_json(list(required_tool_names))
    global_key_json = dump_json(_DISCOVERY_GLOBAL_KEY)
    return f"""
(async () => {{
  const toolNames = {tool_names_json};
  const requiredToolNames = {required_tool_names_json};
  const globalKey = {global_key_json};
  const globalObject = globalThis;

  if (globalObject[globalKey]?.invoke) {{
    const existingMetadata = globalObject[globalKey].metadata();
    const existingToolNames = new Set(existingMetadata.toolNames ?? []);
    if (requiredToolNames.every((name) => existingToolNames.has(name))) {{
      return existingMetadata;
    }}
    delete globalObject[globalKey];
  }}

  const rpcMarkers = ["connect-app-host", "appActions", "bindScope"];

  function referencedScriptUrls() {{
    const urls = new Set();
    for (const script of Array.from(document.scripts || [])) {{
      if (script.src) {{
        urls.add(script.src);
      }}
    }}
    for (const link of Array.from(document.querySelectorAll("link[href]"))) {{
      if (link.href && link.href.includes(".js")) {{
        urls.add(link.href);
      }}
    }}
    for (const entry of performance.getEntriesByType("resource")) {{
      if (typeof entry.name === "string" && entry.name.includes(".js")) {{
        urls.add(entry.name);
      }}
    }}
    return Array.from(urls);
  }}

  function referencedAssetUrlsFromText(text, baseUrl) {{
    const urls = new Set();
    const pattern = /["'`]([^"'`]+\\.js)["'`]/g;
    let match;
    while ((match = pattern.exec(text)) !== null) {{
      const specifier = match[1];
      try {{
        urls.add(new URL(specifier, baseUrl).href);
      }} catch (_error) {{
      }}
    }}
    return Array.from(urls);
  }}

  function assetReferenceRank(url) {{
    const normalized = url.toLowerCase();
    if (normalized.includes("dynamic-tools")) {{
      return 0;
    }}
    if (normalized.includes("app-server")) {{
      return 1;
    }}
    return 2;
  }}

  async function fetchAssetText(url) {{
    try {{
      const response = await fetch(url);
      if (!response.ok) {{
        return null;
      }}
      return await response.text();
    }} catch (_error) {{
      return null;
    }}
  }}

  async function collectAssets(seedUrls) {{
    const assets = [];
    const pending = [...seedUrls];
    const seen = new Set();
    while (pending.length > 0 && seen.size < 500) {{
      const url = pending.shift();
      if (typeof url !== "string" || seen.has(url)) {{
        continue;
      }}
      seen.add(url);
      const text = await fetchAssetText(url);
      if (typeof text === "string") {{
        assets.push({{ url, text }});
        const referencedUrls = referencedAssetUrlsFromText(text, url)
          .sort((left, right) => assetReferenceRank(right) - assetReferenceRank(left));
        for (const referencedUrl of referencedUrls) {{
          if (!seen.has(referencedUrl)) {{
            pending.unshift(referencedUrl);
          }}
        }}
      }}
    }}
    return assets;
  }}

  const assets = await collectAssets(referencedScriptUrls());

  const toolAssets = assets.filter((asset) =>
    asset.text.includes("codex_app") && toolNames.some((name) => asset.text.includes(name))
  );
  const rpcAssets = assets.filter((asset) =>
    rpcMarkers.every((marker) => asset.text.includes(marker))
  );

  if (toolAssets.length === 0) {{
    throw new Error("Could not find Codex app dynamic tool chunk");
  }}
  if (rpcAssets.length === 0) {{
    throw new Error("Could not find Codex app RPC chunk");
  }}

  async function importModules(chunks) {{
    const modules = [];
    for (const chunk of chunks) {{
      try {{
        modules.push({{ url: chunk.url, namespace: await import(chunk.url) }});
      }} catch (_error) {{
      }}
    }}
    return modules;
  }}

  function nestedValues(value, depth = 0, seen = new Set()) {{
    if (value === null || (typeof value !== "object" && typeof value !== "function")) {{
      return [];
    }}
    if (seen.has(value) || depth > 2) {{
      return [];
    }}
    seen.add(value);
    const values = [value];
    for (const child of Object.values(value)) {{
      if (child !== null && (typeof child === "object" || typeof child === "function")) {{
        values.push(...nestedValues(child, depth + 1, seen));
      }}
    }}
    return values;
  }}

  function findAppActions(modules) {{
    for (const moduleRecord of modules) {{
      for (const value of nestedValues(moduleRecord.namespace)) {{
        if (
          value &&
          typeof value === "object" &&
          typeof value.run === "function" &&
          typeof value.bindScope === "function" &&
          value.scope
        ) {{
          return value;
        }}
      }}
    }}
    throw new Error("Could not find Codex appActions object");
  }}

  function stringifyError(error) {{
    if (error && typeof error === "object") {{
      if (typeof error.message === "string") {{
        return error.message;
      }}
      try {{
        return JSON.stringify(error);
      }} catch (_jsonError) {{
        return String(error);
      }}
    }}
    return String(error);
  }}

  async function identifyHandler(candidate, scope) {{
    let validationText = "";
    try {{
      const result = await candidate.handler({{
        scope,
        argumentsValue: "__acodex_invalid_probe__",
        sourceThreadId: "__acodex_probe__",
      }});
      const serialized = typeof result === "string" ? result : JSON.stringify(result);
      validationText = serialized ?? String(result);
    }} catch (error) {{
      validationText = stringifyError(error);
    }}
    for (const name of [...toolNames].sort((left, right) => right.length - left.length)) {{
      const escapedName = name.replace(/[.*+?^${{}}()|[\\]\\\\]/g, "\\\\$&");
      const validationPattern = new RegExp(
        `(?:^|[^A-Za-z0-9_])${{escapedName}}\\\\s+(?:received invalid arguments\\\\.|missing calling thread id\\\\.)`
      );
      if (validationPattern.test(validationText)) {{
        return name;
      }}
    }}
    return null;
  }}

  const toolModules = await importModules(toolAssets);
  const rpcModules = await importModules(rpcAssets);
  const appActions = findAppActions(rpcModules);
  const scope = appActions.scope;
  const handlers = new Map();
  const exportsByTool = {{}};

  for (const moduleRecord of toolModules) {{
    for (const [exportName, handler] of Object.entries(moduleRecord.namespace)) {{
      if (typeof handler !== "function") {{
        continue;
      }}
      const toolName = await identifyHandler({{ exportName, handler }}, scope);
      if (toolName && !handlers.has(toolName)) {{
        handlers.set(toolName, handler);
        exportsByTool[toolName] = exportName;
      }}
    }}
  }}

  const missingToolNames = toolNames.filter((name) => !handlers.has(name));
  const missingRequiredToolNames = requiredToolNames.filter((name) => !handlers.has(name));
  if (missingRequiredToolNames.length > 0) {{
    throw new Error(`Could not discover required Codex app tools: ${{missingRequiredToolNames.join(", ")}}`);
  }}

  const metadata = () => ({{
    toolNames: Array.from(handlers.keys()),
    missingToolNames,
    toolExports: exportsByTool,
    toolChunkUrls: toolAssets.map((asset) => asset.url),
    rpcChunkUrls: rpcAssets.map((asset) => asset.url),
  }});

  globalObject[globalKey] = {{
    metadata,
    async invoke(toolName, argumentsValue, sourceThreadId) {{
      const handler = handlers.get(toolName);
      if (!handler) {{
        throw new Error(`Codex app tool was not discovered: ${{toolName}}`);
      }}
      return await handler({{
        scope,
        argumentsValue,
        sourceThreadId: sourceThreadId ?? undefined,
      }});
    }},
  }};

  return metadata();
}})()
""".strip()


def build_tool_invocation_expression(
    tool_name: str,
    arguments: JsonObject,
    *,
    source_thread_id: str | None = None,
) -> str:
    tool_name_json = dump_json(tool_name)
    arguments_json = dump_json(arguments)
    source_thread_id_json = dump_json(source_thread_id)
    global_key_json = dump_json(_DISCOVERY_GLOBAL_KEY)
    return f"""
(async () => {{
  const backend = globalThis[{global_key_json}];
  if (!backend || typeof backend.invoke !== "function") {{
    throw new Error("Codex app CDP backend has not been discovered");
  }}
  return await backend.invoke({tool_name_json}, {arguments_json}, {source_thread_id_json});
}})()
""".strip()


def parse_tool_discovery_result(value: JsonValue) -> CodexAppToolDiscovery:
    if not isinstance(value, dict):
        raise CodexAppCdpDiscoveryError("Tool discovery result must be a JSON object")

    tool_names = _get_string_tuple(value, "toolNames")
    missing_tool_names = _get_string_tuple(value, "missingToolNames")
    tool_chunk_urls = _get_string_tuple(value, "toolChunkUrls")
    rpc_chunk_urls = _get_string_tuple(value, "rpcChunkUrls")
    tool_exports_value = value.get("toolExports")
    if not isinstance(tool_exports_value, dict):
        raise CodexAppCdpDiscoveryError("Tool discovery result is missing toolExports")

    tool_exports: dict[str, str] = {}
    for tool_name, export_name in tool_exports_value.items():
        if not isinstance(export_name, str):
            raise CodexAppCdpDiscoveryError("Tool discovery export names must be strings")
        tool_exports[tool_name] = export_name

    return CodexAppToolDiscovery(
        tool_names=tool_names,
        missing_tool_names=missing_tool_names,
        tool_exports=tool_exports,
        tool_chunk_urls=tool_chunk_urls,
        rpc_chunk_urls=rpc_chunk_urls,
    )


def _get_string_tuple(mapping: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list):
        raise CodexAppCdpDiscoveryError(f"Tool discovery result is missing {key}")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise CodexAppCdpDiscoveryError(f"Tool discovery result is missing {key}")
        strings.append(item)
    return tuple(strings)
