from __future__ import annotations

import json
from typing import Any


def renderer_expression(payload: dict[str, Any]) -> str:
    """Build the JavaScript expression evaluated inside the Codex renderer.

    Returns:
        A renderer-evaluable JavaScript expression.

    """
    return BRIDGE_EXPRESSION.format(
        bridge_script=BRIDGE_SCRIPT,
        payload=json.dumps(payload),
    )


BRIDGE_EXPRESSION = """
(async () => {{
  const config = {payload};
  {bridge_script}
  return JSON.stringify(await runCodexAppMcpBridge(config));
}})()
"""


BRIDGE_SCRIPT = r"""
function asError(error) {
  if (error instanceof Error) {
    return error.stack || error.message;
  }
  return String(error);
}

function asResult(value) {
  return { ok: true, ...value };
}

function asFailure(error) {
  return { ok: false, error: asError(error) };
}

function descriptorKey(descriptor) {
  return `${descriptor.namespace || "codex_app"}:${descriptor.name}`;
}

function isDescriptor(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    typeof value.name === "string" &&
    typeof value.description === "string" &&
    value.inputSchema &&
    typeof value.inputSchema === "object"
  );
}

function isCodexNamespaceDescriptor(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    value.type === "namespace" &&
    value.name === "codex_app" &&
    Array.isArray(value.tools)
  );
}

function codexDescriptor(descriptor) {
  return {
    ...descriptor,
    namespace: descriptor.namespace || "codex_app",
  };
}

function expandCodexDescriptors(values) {
  const descriptors = [];
  for (const value of values || []) {
    if (value?.namespace === "codex_app" && isDescriptor(value)) {
      descriptors.push(codexDescriptor(value));
      continue;
    }

    if (!isCodexNamespaceDescriptor(value)) continue;
    for (const tool of value.tools) {
      if (isDescriptor(tool)) {
        descriptors.push(codexDescriptor(tool));
      }
    }
  }
  return descriptors;
}

function toMcpTool(descriptor) {
  return {
    name: `codex_app.${descriptor.name}`,
    title: descriptor.title || `codex_app.${descriptor.name}`,
    description: descriptor.description,
    inputSchema: descriptor.inputSchema || { type: "object", properties: {} },
    annotations: descriptor.annotations,
  };
}

function resultText(result) {
  const items = result?.contentItems;
  if (!Array.isArray(items)) {
    return "";
  }
  return items
    .filter((item) => item?.type === "inputText" && typeof item.text === "string")
    .map((item) => item.text)
    .join("\n");
}

function noHandler(toolName) {
  return {
    success: false,
    contentItems: [
      {
        type: "inputText",
        text:
          `Codex exposed the ${toolName} descriptor, but this build did not export a callable renderer handler for it. ` +
          `If the Electron MCP host implements call-mcp-tool in a newer build, this proxy will use it automatically.`,
      },
    ],
  };
}

async function loadModules(config) {
  const [dynamicTools, manager, appScope, vscodeApi] = await Promise.all([
    import(config.assets.dynamicToolsUrl),
    import(config.assets.managerUrl),
    import(config.assets.appScopeUrl),
    config.assets.vscodeApiUrl ? import(config.assets.vscodeApiUrl) : Promise.resolve(null),
  ]);
  return { dynamicTools, manager, appScope, vscodeApi };
}

function findScopeChain() {
  const roots = [];
  const domNodes = [
    document.getElementById("root"),
    document.body,
    document.documentElement,
    ...Array.from(document.querySelectorAll("*")).slice(0, 10000),
  ].filter(Boolean);
  for (const node of domNodes) {
    for (const key of Object.keys(node)) {
      if (key.startsWith("__reactContainer$") || key.startsWith("__reactFiber$")) {
        const fiber = node[key];
        if (fiber) roots.push(fiber);
      }
    }
  }
  if (globalThis.__codexRoot?._internalRoot?.current) {
    roots.push(globalThis.__codexRoot._internalRoot.current);
  }

  const stack = roots;
  const seenFibers = new Set();
  let best = null;
  let bestScore = -1;

  function consider(value) {
    if (!(value instanceof Map)) return;
    const nodes = Array.from(value.values());
    const signalNodeCount = nodes.filter((node) => node?.familyBindings && node?.store).length;
    if (signalNodeCount === 0) return;
    const hasQueryClient = nodes.some((node) => node?.queryClient);
    const score = signalNodeCount * 10 + value.size + (hasQueryClient ? 100 : 0);
    if (score > bestScore) {
      best = value;
      bestScore = score;
    }
  }

  function scanObject(value, depth, seenObjects) {
    if (!value || typeof value !== "object" || depth > 3 || seenObjects.has(value)) return;
    seenObjects.add(value);
    consider(value);
    if (value instanceof Map) return;
    for (const key of Object.keys(value).slice(0, 80)) {
      if (key === "return" || key === "child" || key === "sibling" || key === "alternate" || key === "stateNode") {
        continue;
      }
      try {
        scanObject(value[key], depth + 1, seenObjects);
      } catch {
        // Ignore getters from React internals.
      }
    }
  }

  while (stack.length > 0) {
    const fiber = stack.pop();
    if (!fiber || seenFibers.has(fiber)) continue;
    seenFibers.add(fiber);
    scanObject(fiber.memoizedProps, 0, new Set());
    scanObject(fiber.pendingProps, 0, new Set());
    scanObject(fiber.memoizedState, 0, new Set());
    scanObject(fiber.dependencies, 0, new Set());

    if (fiber.child) stack.push(fiber.child);
    if (fiber.sibling) stack.push(fiber.sibling);
    if (fiber.alternate) stack.push(fiber.alternate);
  }

  if (!best) {
    throw new Error("Could not locate the Codex app scope in the renderer");
  }
  return best;
}

function makeScope(appScopeModule) {
  const chain = findScopeChain();
  const fallbackNode = Array.from(chain.values()).find((node) => node?.store) || Array.from(chain.values())[0];
  const rootScopeId = appScopeModule?.t?.id;
  const rootNode = (rootScopeId && chain.get(rootScopeId)) || fallbackNode;

  function nodeFor(signal) {
    return chain.get(signal?.scope?.id) || rootNode || fallbackNode;
  }

  return {
    get queryClient() {
      return rootNode?.queryClient || fallbackNode?.queryClient || null;
    },
    get(signal, key) {
      const node = nodeFor(signal);
      if (arguments.length >= 2) {
        if (typeof signal?.read === "function") {
          return signal.read(node, chain, key);
        }
        if (typeof signal?.resolve === "function") {
          const binding = signal.resolve(node, chain, key);
          return node.store.get(binding);
        }
      }
      if (typeof signal?.get === "function") {
        return signal.get();
      }
      if (typeof signal?.resolve === "function") {
        const binding = signal.resolve(node, chain);
        return node.store.get(binding);
      }
      throw new Error("Unsupported Codex signal read");
    },
    set(signal, ...args) {
      const node = nodeFor(signal);
      if (typeof signal?.resolve !== "function") {
        throw new Error("Unsupported Codex signal write");
      }
      const binding = args.length > 1 ? signal.resolve(node, chain, args[0]) : signal.resolve(node, chain);
      const values = args.length > 1 ? args.slice(1) : args;
      return node.store.set(binding, ...values);
    },
    read(signal, key) {
      return this.get(signal, key);
    },
  };
}

function featureOverrides(dynamicTools, manager) {
  const overrides = {
    automation_update: true,
    open_in_codex: true,
    realtime_conversation: true,
    thread_tools: true,
  };
  for (const value of [...Object.values(dynamicTools), ...Object.values(manager)]) {
    if (typeof value === "string" && /^[a-z][a-z0-9_:-]*$/.test(value)) {
      overrides[value] = true;
    }
  }
  return overrides;
}

async function findDescriptorFactory(dynamicTools, manager, hostId) {
  const args = descriptorFactoryArgs(dynamicTools, manager, hostId);

  for (const fn of Object.values(dynamicTools)) {
    if (typeof fn !== "function") continue;
    try {
      const result = await fn(args);
      if (Array.isArray(result) && expandCodexDescriptors(result).length > 0) {
        return fn;
      }
    } catch {
      // Most exports are not descriptor factories.
    }
  }
  return null;
}

function descriptorFactoryArgs(dynamicTools, manager, hostId) {
  return {
    availableHandoffHosts: [],
    authMethod: null,
    crossHostHandoffEnabled: true,
    featureOverrides: featureOverrides(dynamicTools, manager),
    hostId,
    isAuthLoading: false,
    listExperimentalFeatures: async () => ({
      data: [
        { name: "workspace_dependencies", enabled: true },
        { name: "automation_update", enabled: true },
        { name: "apps", enabled: true },
      ],
      nextCursor: null,
    }),
    listModels: async () => ({ data: [], nextCursor: null }),
    modelAvailabilityConfig: {
      availableModels: [],
      defaultModel: null,
      useHiddenModels: true,
    },
  };
}

async function listCodexDescriptors(dynamicTools, manager, hostId) {
  const descriptors = new Map();
  const factory = await findDescriptorFactory(dynamicTools, manager, hostId);
  if (factory) {
    const dynamicDescriptors = await factory(descriptorFactoryArgs(dynamicTools, manager, hostId));
    for (const descriptor of expandCodexDescriptors(dynamicDescriptors)) {
      descriptors.set(descriptorKey(descriptor), descriptor);
    }
  }

  for (const descriptor of Object.values(manager)) {
    if (!isDescriptor(descriptor)) continue;
    const normalized = codexDescriptor(descriptor);
    const alreadyKnown = descriptors.has(descriptorKey(normalized));
    const managerOnlyCodexTool =
      normalized.name === "read_thread_terminal" ||
      normalized.name === "load_workspace_dependencies" ||
      normalized.name === "automation_update";
    if (alreadyKnown || managerOnlyCodexTool) {
      descriptors.set(descriptorKey(normalized), normalized);
    }
  }

  return Array.from(descriptors.values()).sort((a, b) => a.name.localeCompare(b.name));
}

function shouldProbeDynamicHandler(fn) {
  const source = safeFunctionSource(fn);
  return (
    source.includes("argumentsValue") ||
    source.includes("received invalid arguments") ||
    source.includes("safeParse")
  );
}

function shouldProbeManagerHandler(fn) {
  const source = safeFunctionSource(fn);
  return (
    source.includes("takes no arguments") ||
    source.includes("read_thread_terminal") ||
    source.includes("load_workspace_dependencies")
  );
}

function safeFunctionSource(fn) {
  try {
    return Function.prototype.toString.call(fn);
  } catch {
    return "";
  }
}

async function safeInvoke(fn, ...values) {
  try {
    return await fn(...values);
  } catch (error) {
    return {
      success: false,
      contentItems: [{ type: "inputText", text: asError(error) }],
    };
  }
}

function looksLikeAppServerManager(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    typeof value.getHostId === "function" &&
    typeof value.getConversation === "function"
  );
}

function discoverAppServerManagers(dynamicTools, manager, scope) {
  const managers = [];
  for (const exported of [...Object.values(dynamicTools), ...Object.values(manager)]) {
    try {
      const value = scope.get(exported);
      if (Array.isArray(value)) {
        for (const item of value) {
          if (looksLikeAppServerManager(item) && !managers.includes(item)) managers.push(item);
        }
      } else if (looksLikeAppServerManager(value) && !managers.includes(value)) {
        managers.push(value);
      }
    } catch {
      // Most exports are not scope signals.
    }
  }
  return managers;
}

function makeAppServerRegistry(dynamicTools, manager, scope) {
  const managers = discoverAppServerManagers(dynamicTools, manager, scope);
  return {
    getMaybeForConversationId(conversationId) {
      return managers.find((candidate) => {
        try {
          return candidate.getConversation(conversationId) != null;
        } catch {
          return false;
        }
      }) || null;
    },
    getDefault() {
      return managers.find((candidate) => {
        try {
          return candidate.getHostId() === "local";
        } catch {
          return false;
        }
      }) || managers[0] || null;
    },
  };
}

function makeCallContext(scope, args, sourceThreadId, appServerRegistry = null) {
  return {
    appServerRegistry,
    argumentsValue: args,
    callId:
      typeof crypto?.randomUUID === "function"
        ? crypto.randomUUID()
        : `codex-mcp-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    callingThreadId: sourceThreadId || null,
    queryClient: scope.queryClient,
    scope,
    sourceThreadId: sourceThreadId || null,
    threadId: sourceThreadId || null,
  };
}

async function inferSourceThreadId(dynamicTools, scope, handlerMap, configuredSourceThreadId) {
  if (configuredSourceThreadId) {
    return configuredSourceThreadId;
  }
  const listThreadsHandler = handlerMap.get("list_threads");
  if (!listThreadsHandler || listThreadsHandler.kind !== "dynamic") {
    return null;
  }
  const result = await safeInvoke(
    listThreadsHandler.fn,
    makeCallContext(scope, { limit: 1 }, null)
  );
  try {
    const text = resultText(result);
    const parsed = JSON.parse(text);
    const thread = parsed?.threads?.[0] || parsed?.data?.[0] || parsed?.[0];
    return thread?.threadId || thread?.id || null;
  } catch {
    return null;
  }
}

async function buildHandlerMap(dynamicTools, manager, descriptors, scope, sourceThreadId) {
  const wantedNames = new Set(descriptors.map((descriptor) => descriptor.name));
  return await buildHandlerMapForNames(dynamicTools, manager, wantedNames, scope, sourceThreadId);
}

async function buildHandlerMapForNames(dynamicTools, manager, wantedNames, scope, sourceThreadId) {
  const map = new Map();
  const probeArgs = { __codex_mcp_probe__: true };

  for (const fn of Object.values(dynamicTools)) {
    if (typeof fn !== "function" || !shouldProbeDynamicHandler(fn)) continue;
    const result = await safeInvoke(fn, makeCallContext(scope, probeArgs, sourceThreadId));
    const text = resultText(result);
    for (const name of wantedNames) {
      if (!map.has(name) && text.includes(name)) {
        map.set(name, { kind: "dynamic", fn });
      }
    }
  }
  if (hasAllHandlers(map, wantedNames)) {
    return map;
  }

  for (const fn of Object.values(manager)) {
    if (typeof fn !== "function" || !shouldProbeManagerHandler(fn)) continue;
    const result = await safeInvoke(fn, probeArgs, sourceThreadId);
    const text = resultText(result);
    for (const name of wantedNames) {
      if (!map.has(name) && text.includes(name)) {
        map.set(name, { kind: "managerPositionalThread", fn });
      }
    }
  }

  return map;
}

function hasAllHandlers(map, wantedNames) {
  for (const name of wantedNames) {
    if (!map.has(name)) return false;
  }
  return true;
}

async function callRendererHandler(modules, config, toolName, args) {
  const { dynamicTools, manager, appScope } = modules;
  const scope = makeScope(appScope);
  const appServerRegistry = makeAppServerRegistry(dynamicTools, manager, scope);
  const descriptors = await listCodexDescriptors(dynamicTools, manager, config.hostId);
  const descriptor = descriptors.find((item) => item.name === toolName);
  if (!descriptor) {
    return {
      success: false,
      contentItems: [{ type: "inputText", text: `Unknown codex_app tool: ${toolName}` }],
    };
  }

  const wantedNames = handlerProbeNames(toolName, descriptors);
  let handlerMap = await buildHandlerMapForNames(
    dynamicTools,
    manager,
    wantedNames,
    scope,
    config.sourceThreadId
  );
  const sourceThreadId = await resolveSourceThreadId(
    toolName,
    args,
    config,
    dynamicTools,
    scope,
    handlerMap
  );
  handlerMap = await buildHandlerMapForNames(
    dynamicTools,
    manager,
    wantedNames,
    scope,
    sourceThreadId
  );
  const handler = handlerMap.get(toolName);
  if (!handler) {
    return noHandler(toolName);
  }
  if (handler.kind === "managerPositionalThread") {
    return await safeInvoke(handler.fn, args, sourceThreadId);
  }
  return await safeInvoke(handler.fn, makeCallContext(scope, args, sourceThreadId, appServerRegistry));
}

async function resolveSourceThreadId(toolName, args, config, dynamicTools, scope, handlerMap) {
  if (args?.threadId || config.sourceThreadId) {
    return args?.threadId || config.sourceThreadId;
  }
  if (toolName === "list_threads") {
    return null;
  }
  return await inferSourceThreadId(dynamicTools, scope, handlerMap, null);
}

function handlerProbeNames(toolName, descriptors) {
  const descriptorNames = new Set(descriptors.map((descriptor) => descriptor.name));
  return new Set([toolName, "list_threads"].filter((name) => descriptorNames.has(name)));
}

async function runCodexAppMcpBridge(config) {
  try {
    const modules = await loadModules(config);
    const descriptors = await listCodexDescriptors(
      modules.dynamicTools,
      modules.manager,
      config.hostId
    );

    if (config.action === "listTools") {
      return asResult({
        tools: descriptors.map(toMcpTool),
      });
    }

    if (config.action !== "callTool") {
      throw new Error(`Unsupported bridge action: ${config.action}`);
    }

    const toolName = config.toolName;
    const args = config.arguments || {};
    const result = await callRendererHandler(modules, config, toolName, args);
    return asResult({ result });
  } catch (error) {
    return asFailure(error);
  }
}
"""
