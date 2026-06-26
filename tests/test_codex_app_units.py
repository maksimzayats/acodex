from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

from acodex.core.codex_app import assets, bridge, runtime_dependencies
from acodex.core.codex_app.assets import (
    CodexRendererAssetDiscoveryError,
    CodexRendererAssets,
    discover_renderer_assets,
)
from acodex.core.codex_app.bridge import (
    CodexAppBridge,
    CodexAppBridgeError,
    CodexAppBridgeSettings,
    normalize_tool_name,
)
from acodex.core.codex_app.cdp import CodexCDPClient, CodexCDPError
from acodex.core.codex_app.renderer_bridge import BRIDGE_SCRIPT, renderer_expression


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeCDP:
    def __init__(
        self,
        *,
        tree: dict[str, Any] | None = None,
        contents: dict[str, str | BaseException] | None = None,
        evaluate_result: Any = None,
        evaluate_results: list[Any] | None = None,
    ) -> None:
        self.tree = tree or {}
        self.contents = contents or {}
        self.evaluate_result = evaluate_result
        self.evaluate_results = evaluate_results or []
        self.evaluations: list[tuple[str, bool]] = []

    async def resource_tree(self) -> dict[str, Any]:
        return self.tree

    async def resource_content(self, frame_id: str, url: str) -> str:
        result = self.contents[url]
        if isinstance(result, BaseException):
            raise result
        return result

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> Any:
        self.evaluations.append((expression, await_promise))
        if self.evaluate_results:
            return self.evaluate_results.pop(0)
        return self.evaluate_result


def frame_tree(resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {"frameTree": {"frame": {"id": "frame-1"}, "resources": resources}}


def test_renderer_assets_payload_and_discovery_from_resource_tree() -> None:
    renderer_assets = CodexRendererAssets(
        app_scope_url="app://-/scope.js",
        dynamic_tools_url="app://-/dynamic.js",
        manager_url="app://-/manager.js",
        vscode_api_url=None,
    )
    assert renderer_assets.as_payload() == {
        "appScopeUrl": "app://-/scope.js",
        "dynamicToolsUrl": "app://-/dynamic.js",
        "managerUrl": "app://-/manager.js",
        "vscodeApiUrl": None,
    }

    cdp = FakeCDP(
        tree=frame_tree(
            [
                {"url": "https://example.com/not-app.js", "type": "Script"},
                {"url": "app://-/scope.js", "mimeType": "application/javascript"},
                {"url": "app://-/dynamic.js", "type": "Script"},
                {"url": "app://-/manager.js", "urlFragment": "unused"},
                {"url": "app://-/vscode.js", "type": "Script"},
                {"url": "app://-/bad.js", "type": "Script"},
            ],
        ),
        contents={
            "app://-/scope.js": "queryClient familyBindings __scopeBrand",
            "app://-/dynamic.js": "codex_app list_threads send_message_to_thread",
            "app://-/manager.js": "read_thread_terminal load_workspace_dependencies",
            "app://-/vscode.js": "vscode://codex/ sendMessageFromView",
            "app://-/bad.js": CodexCDPError("ignore unreadable resource"),
        },
    )

    discovered = run(discover_renderer_assets(cast("CodexCDPClient", cdp)))
    assert discovered == CodexRendererAssets(
        app_scope_url="app://-/scope.js",
        dynamic_tools_url="app://-/dynamic.js",
        manager_url="app://-/manager.js",
        vscode_api_url="app://-/vscode.js",
    )


def test_renderer_asset_discovery_falls_back_to_renderer_scan() -> None:
    cdp = FakeCDP(
        tree=frame_tree([{"url": "app://-/scope.js", "type": "Script"}]),
        contents={"app://-/scope.js": "queryClient familyBindings Missing query client"},
        evaluate_result={
            "dynamic_tools": "app://-/dynamic.js",
            "manager": "app://-/manager.js",
            "vscode_api": "app://-/vscode.js",
        },
    )
    discovered = run(discover_renderer_assets(cast("CodexCDPClient", cdp)))
    assert discovered.dynamic_tools_url == "app://-/dynamic.js"
    assert discovered.manager_url == "app://-/manager.js"
    assert discovered.vscode_api_url == "app://-/vscode.js"
    assert cdp.evaluations[0][1] is True

    cdp.evaluate_result = json.dumps(
        {
            "app_scope": "app://-/scope.js",
            "dynamic_tools": "app://-/dynamic.js",
            "manager": "app://-/manager.js",
        },
    )
    assert run(assets.RendererFallbackScanner().scan(cast("CodexCDPClient", cdp))) == {
        "app_scope": "app://-/scope.js",
        "dynamic_tools": "app://-/dynamic.js",
        "manager": "app://-/manager.js",
    }


def test_renderer_asset_discovery_errors_and_helpers() -> None:
    with pytest.raises(CodexRendererAssetDiscoveryError, match="no frame tree"):
        run(discover_renderer_assets(cast("CodexCDPClient", FakeCDP(tree={}))))

    with pytest.raises(CodexRendererAssetDiscoveryError, match="dynamic_tools, manager"):
        run(
            discover_renderer_assets(
                cast(
                    "CodexCDPClient",
                    FakeCDP(
                        tree=frame_tree([{"url": "app://-/scope.js", "type": "Script"}]),
                        contents={"app://-/scope.js": "queryClient familyBindings __scopeBrand"},
                        evaluate_result={},
                    ),
                ),
            ),
        )

    assert assets.AssetMatchRecorder().missing_required({"app_scope": "x"}) == [
        "dynamic_tools",
        "manager",
    ]
    assert assets.string_dict("not a dict") == {}
    assert assets.string_dict({"good": "value", "bad": 1, 2: "number-key"}) == {
        "good": "value",
        "2": "number-key",
    }
    resources = assets.ResourceTreeScanner().collect({
        "frame": {"id": "root"},
        "resources": [
            {"url": "app://-/a.js"},
            {"url": "app://-/b", "type": "Script"},
            {"url": "app://-/c", "mimeType": "text/javascript"},
            {"url": "app://-/style.css", "type": "Stylesheet"},
            {"url": 1, "type": "Script"},
            "bad",
        ],
        "childFrames": [
            {
                "frame": {"id": 1},
                "resources": [{"url": "app://-/ignored.js"}],
            },
            {
                "frame": {"id": "child"},
                "resources": [{"url": "app://-/child.js"}],
                "childFrames": ["bad"],
            },
        ],
    })
    assert [(resource.frame_id, resource.url) for resource in resources] == [
        ("root", "app://-/a.js"),
        ("root", "app://-/b"),
        ("root", "app://-/c"),
        ("child", "app://-/child.js"),
    ]
    assert (
        assets.ResourceTreeScanner().collect({
            "frame": "bad",
            "resources": "bad",
            "childFrames": "bad",
        })
        == []
    )
    assert (
        assets.ResourceTreeScanner().collect({
            "frame": {"id": "root"},
            "resources": "bad",
        })
        == []
    )


def test_bridge_lists_and_calls_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    cdp = FakeCDP(
        evaluate_result=json.dumps(
            {
                "ok": True,
                "tools": [{"name": "codex_app.echo"}, "bad"],
                "result": {"contentItems": [{"type": "inputText", "text": "ok"}]},
            },
        ),
    )
    monkeypatch.setattr(
        bridge,
        "discover_renderer_assets",
        lambda _cdp: asyncio.sleep(
            0,
            CodexRendererAssets(
                app_scope_url="scope",
                dynamic_tools_url="dynamic",
                manager_url="manager",
                vscode_api_url=None,
            ),
        ),
    )
    app_bridge = CodexAppBridge(
        _cdp=cast("CodexCDPClient", cdp),
        _settings=CodexAppBridgeSettings(host_id="host", source_thread_id="thread"),
    )

    assert run(app_bridge.list_tools()) == [{"name": "codex_app.echo"}]
    assert run(app_bridge.call_tool("codex_app__echo", {"value": 1})) == {
        "contentItems": [{"type": "inputText", "text": "ok"}],
    }

    expression, await_promise = cdp.evaluations[-1]
    assert await_promise is True
    assert '"toolName": "echo"' in expression
    assert '"sourceThreadId": "thread"' in expression


def test_bridge_rediscovers_assets_after_stale_import_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cdp = FakeCDP(
        evaluate_results=[
            {
                "ok": False,
                "error": (
                    "TypeError: Failed to fetch dynamically imported module: app://-/assets/old.js"
                ),
            },
            {"ok": True, "tools": [{"name": "codex_app.echo"}]},
        ],
    )
    discovered_assets = [
        CodexRendererAssets("scope-1", "dynamic-1", "manager-1", None),
        CodexRendererAssets("scope-2", "dynamic-2", "manager-2", "vscode-2"),
    ]

    async def discover(_cdp: CodexCDPClient) -> CodexRendererAssets:
        await asyncio.sleep(0)
        return discovered_assets.pop(0)

    monkeypatch.setattr(bridge, "discover_renderer_assets", discover)
    app_bridge = CodexAppBridge(
        _cdp=cast("CodexCDPClient", cdp),
        _settings=CodexAppBridgeSettings(),
    )

    assert run(app_bridge.list_tools()) == [{"name": "codex_app.echo"}]
    assert len(cdp.evaluations) == 2
    assert '"dynamicToolsUrl": "dynamic-1"' in cdp.evaluations[0][0]
    assert '"dynamicToolsUrl": "dynamic-2"' in cdp.evaluations[1][0]


def test_bridge_handles_invalid_results_and_workspace_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cdp = FakeCDP(evaluate_result={"ok": True, "result": "raw"})
    app_bridge = CodexAppBridge(
        _cdp=cast("CodexCDPClient", cdp),
        _settings=CodexAppBridgeSettings(),
    )
    app_bridge._assets = CodexRendererAssets("scope", "dynamic", "manager", "vscode")
    assert run(app_bridge.call_tool("echo", None)) == {
        "success": False,
        "contentItems": [{"type": "inputText", "text": "raw"}],
    }

    fallback = {"success": True, "contentItems": [{"type": "inputText", "text": "fallback"}]}
    cdp.evaluate_result = {
        "ok": True,
        "result": {
            "success": False,
            "contentItems": [
                {"type": "inputText", "text": "did not export a callable renderer handler"},
            ],
        },
    }
    monkeypatch.setattr(bridge, "load_workspace_dependencies_fallback", lambda: fallback)
    assert run(app_bridge.call_tool("codex_app.load_workspace_dependencies", {})) == fallback

    cdp.evaluate_result = {"ok": True, "tools": "not a list"}
    assert run(app_bridge.list_tools()) == []

    cdp.evaluate_result = ["not", "a dict"]
    with pytest.raises(CodexAppBridgeError, match="Unexpected Codex bridge result"):
        run(app_bridge.list_tools())

    cdp.evaluate_result = {"ok": False, "error": "failed"}
    with pytest.raises(CodexAppBridgeError, match="failed"):
        run(app_bridge.list_tools())

    cdp.evaluate_result = {"ok": False}
    with pytest.raises(CodexAppBridgeError, match="Codex bridge failed"):
        run(app_bridge.list_tools())


def test_tool_name_normalization_and_renderer_expression() -> None:
    assert normalize_tool_name("codex_app.echo") == "echo"
    assert normalize_tool_name("codex_app__echo") == "echo"
    assert normalize_tool_name("echo") == "echo"

    expression = renderer_expression({"action": "listTools"})
    assert '"action": "listTools"' in expression
    assert "descriptorFactoryArgs" in BRIDGE_SCRIPT
    assert "runCodexAppMcpBridge" in expression


def test_renderer_bridge_guards_function_source_probe_failures() -> None:
    assert "function safeFunctionSource(fn)" in BRIDGE_SCRIPT
    assert 'catch {\n    return "";' in BRIDGE_SCRIPT
    assert BRIDGE_SCRIPT.count("Function.prototype.toString.call") == 1
    assert "const source = safeFunctionSource(fn);" in BRIDGE_SCRIPT


def test_renderer_bridge_probes_only_needed_handlers_for_tool_calls() -> None:
    assert "function handlerProbeNames(toolName, descriptors)" in BRIDGE_SCRIPT
    assert 'new Set([toolName, "list_threads"].filter' in BRIDGE_SCRIPT
    assert "await buildHandlerMapForNames(\n    dynamicTools," in BRIDGE_SCRIPT


def test_renderer_bridge_does_not_infer_source_thread_for_list_threads() -> None:
    assert (
        "function resolveSourceThreadId(toolName, args, config, dynamicTools, scope, handlerMap)"
        in (BRIDGE_SCRIPT)
    )
    assert 'if (toolName === "list_threads") {\n    return null;' in BRIDGE_SCRIPT


def test_renderer_bridge_uses_live_handlers_instead_of_internal_mcp_calls() -> None:
    assert "list-mcp-server-status" not in BRIDGE_SCRIPT
    assert '"call-mcp-tool"' not in BRIDGE_SCRIPT
    assert "const result = await callRendererHandler(modules, config, toolName, args);" in (
        BRIDGE_SCRIPT
    )


def test_runtime_dependency_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not runtime_dependencies.is_descriptor_without_handler({"success": True})
    assert not runtime_dependencies.is_descriptor_without_handler(
        {"success": False, "contentItems": "not a list"},
    )
    assert not runtime_dependencies.is_descriptor_without_handler(
        {"success": False, "contentItems": [{"text": "other"}, {"text": 1}]},
    )
    assert runtime_dependencies.is_descriptor_without_handler(
        {
            "success": False,
            "contentItems": [
                "bad",
                {"text": "did not export a callable renderer handler"},
            ],
        },
    )

    monkeypatch.setattr(runtime_dependencies.Path, "home", lambda: tmp_path)
    missing = runtime_dependencies.load_workspace_dependencies_fallback()
    assert missing["success"] is False
    assert "No Codex runtime" in missing["contentItems"][0]["text"]

    cache = tmp_path / ".cache" / "codex-runtimes"
    older = cache / "older"
    newer = cache / "newer"
    incomplete = cache / "incomplete"
    for root in (older, newer, incomplete):
        root.mkdir(parents=True)
        (root / "runtime.json").write_text('{"bundleVersion": "1.0"}')
    (older / "dependencies" / "node").mkdir(parents=True)
    (older / "dependencies" / "python").mkdir()
    (newer / "dependencies" / "node").mkdir(parents=True)
    (newer / "dependencies" / "python").mkdir()
    (incomplete / "dependencies" / "node").mkdir(parents=True)
    (newer / "runtime.json").write_text('{"bundleVersion": "2.0"}')

    result = runtime_dependencies.load_workspace_dependencies_fallback()
    assert result["success"] is True
    text = result["contentItems"][0]["text"]
    assert "Bundle version: `2.0`" in text
    assert str(newer / "dependencies" / "node" / "bin" / "node") in text

    for child in cache.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
    incomplete.mkdir()
    (incomplete / "runtime.json").write_text("{}")
    (incomplete / "dependencies" / "node").mkdir(parents=True)
    assert runtime_dependencies._find_codex_runtime_root() is None
