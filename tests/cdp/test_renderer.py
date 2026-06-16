from __future__ import annotations

import pytest

from acodex.core.asyncio.cdp.errors import CodexAppCdpDiscoveryError
from acodex.core.asyncio.cdp.renderer import (
    ALL_CODEX_APP_THREAD_TOOL_NAMES,
    build_tool_discovery_expression,
    build_tool_invocation_expression,
    parse_tool_discovery_result,
)
from acodex.core.asyncio.cdp.types import JsonValue
from tests.cdp.helpers import discovery_result


def test_discovery_expression_contains_robust_renderer_markers() -> None:
    expression = build_tool_discovery_expression()

    for tool_name in ALL_CODEX_APP_THREAD_TOOL_NAMES:
        assert f'"{tool_name}"' in expression
    assert "codex_app" in expression
    assert "connect-app-host" in expression
    assert "appActions" in expression
    assert "bindScope" in expression
    assert 'document.querySelectorAll("link[href]")' in expression
    assert 'link.href.includes(".js")' in expression
    assert "referencedAssetUrlsFromText(text, baseUrl)" in expression
    assert "assetReferenceRank(url)" in expression
    assert "new URL(specifier, baseUrl).href" in expression
    assert "const assets = await collectAssets(referencedScriptUrls())" in expression
    assert "seen.size < 500" in expression
    assert "requiredToolNames.every((name) => existingToolNames.has(name))" in expression
    assert "delete globalObject[globalKey]" in expression
    assert "serialized ?? String(result)" in expression
    assert "__acodex_invalid_probe__" in expression
    assert "__acodexCdpBackendV2" in expression
    assert "sort((left, right) => right.length - left.length)" in expression
    assert "validationPattern.test(validationText)" in expression
    assert "validationText.includes(name)" not in expression


def test_invocation_expression_uses_renderer_native_payload_keys() -> None:
    expression = build_tool_invocation_expression(
        "read_thread",
        {"threadId": "thread-1", "turnLimit": 3, "includeOutputs": False},
        source_thread_id="source-1",
    )

    assert 'backend.invoke("read_thread"' in expression
    assert '"threadId":"thread-1"' in expression
    assert '"turnLimit":3' in expression
    assert '"includeOutputs":false' in expression
    assert '"source-1"' in expression
    assert "thread_id" not in expression
    assert "turn_limit" not in expression
    assert "include_outputs" not in expression


def test_parse_tool_discovery_result_returns_metadata() -> None:
    discovery = parse_tool_discovery_result(discovery_result(("list_threads",)))

    assert discovery.tool_names == ("list_threads",)
    assert discovery.missing_tool_names == tuple(
        name for name in ALL_CODEX_APP_THREAD_TOOL_NAMES if name != "list_threads"
    )
    assert discovery.tool_exports == {"list_threads": "a"}
    assert discovery.tool_chunk_urls == ("app://-/assets/tools.js",)
    assert discovery.rpc_chunk_urls == ("app://-/assets/rpc.js",)


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("bad", "JSON object"),
        (
            {"toolNames": [], "missingToolNames": [], "toolChunkUrls": [], "rpcChunkUrls": []},
            "toolExports",
        ),
        (
            {
                "toolNames": [],
                "missingToolNames": [],
                "toolChunkUrls": [],
                "rpcChunkUrls": [],
                "toolExports": {"list_threads": 1},
            },
            "export names",
        ),
        (
            {
                "missingToolNames": [],
                "toolChunkUrls": [],
                "rpcChunkUrls": [],
                "toolExports": {},
            },
            "toolNames",
        ),
    ],
)
def test_parse_tool_discovery_result_rejects_invalid_metadata(value: JsonValue, match: str) -> None:
    with pytest.raises(CodexAppCdpDiscoveryError, match=match):
        parse_tool_discovery_result(value)
