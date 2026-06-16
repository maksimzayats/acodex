from __future__ import annotations

import asyncio
import json
from typing import get_type_hints

import pytest
from typing_extensions import Unpack

from acodex import (
    ALL_CODEX_APP_THREAD_TOOL_NAMES,
    CdpTarget,
    CodexAppCdpClient,
    CodexAppCdpConnectionError,
    CodexAppCdpDiscoveryError,
    CodexAppCdpSettings,
    JsonObject,
)
from acodex.asyncio.cdp import runtime as cdp_runtime
from acodex.asyncio.cdp.runtime import CdpRuntimeEvaluator
from acodex.asyncio.tools.read_thread import ReadThreadToolInput
from tests.cdp.helpers import (
    FakeRuntime,
    FakeWebSocket,
    client_with_runtime,
    discovery_result,
    renderer_success,
)

LIST_THREADS_OUTPUT: JsonObject = {
    "schemaVersion": 1,
    "query": "active",
    "threads": [
        {
            "id": "thread-1",
            "title": "Thread title",
            "preview": "Preview",
            "status": "idle",
            "cwd": "/repo",
            "createdAt": 10,
            "updatedAt": 20,
        },
    ],
}

READ_THREAD_OUTPUT: JsonObject = {
    "schemaVersion": 1,
    "thread": {
        "id": "thread-1",
        "title": "Thread title",
        "preview": "Preview",
        "status": {"type": "idle"},
        "cwd": "/repo",
        "createdAt": 10,
        "updatedAt": 20,
    },
    "page": {"order": "newest_first", "limit": 4, "nextCursor": None, "hasMore": False},
    "turns": [],
}


def test_public_read_thread_signature_is_snake_case() -> None:
    type_hints = get_type_hints(CodexAppCdpClient.read_thread, include_extras=True)
    read_thread_keys = ReadThreadToolInput.__annotations__.keys()

    assert type_hints["arguments"] == Unpack[ReadThreadToolInput]
    assert "thread_id" in read_thread_keys
    assert "turn_limit" in read_thread_keys
    assert "include_outputs" in read_thread_keys
    assert "max_output_chars_per_item" in read_thread_keys
    assert "threadId" not in read_thread_keys
    assert "turnLimit" not in read_thread_keys
    assert "includeOutputs" not in read_thread_keys
    assert "maxOutputCharsPerItem" not in read_thread_keys


def test_read_only_wrappers_translate_to_renderer_payload() -> None:
    runtime = FakeRuntime(
        responses=[
            discovery_result(ALL_CODEX_APP_THREAD_TOOL_NAMES),
            renderer_success(LIST_THREADS_OUTPUT),
            renderer_success(READ_THREAD_OUTPUT),
        ],
    )
    client = client_with_runtime(runtime)

    list_result = asyncio.run(client.list_threads(limit=5, query="active"))
    read_result = asyncio.run(
        client.read_thread(
            thread_id="thread-1",
            cursor="cursor-1",
            include_outputs=True,
            max_output_chars_per_item=120,
            turn_limit=4,
        ),
    )

    assert list_result.model_dump() == {
        "schema_version": 1,
        "query": "active",
        "threads": [
            {
                "id": "thread-1",
                "title": "Thread title",
                "preview": "Preview",
                "status": "idle",
                "cwd": "/repo",
                "created_at": 10,
                "updated_at": 20,
            },
        ],
    }
    assert read_result.model_dump() == {
        "schema_version": 1,
        "thread": {
            "id": "thread-1",
            "title": "Thread title",
            "preview": "Preview",
            "status": {"type": "idle"},
            "cwd": "/repo",
            "created_at": 10,
            "updated_at": 20,
        },
        "page": {
            "order": "newest_first",
            "limit": 4,
            "next_cursor": None,
            "has_more": False,
        },
        "turns": [],
    }
    assert '"limit":5' in runtime.expressions[1]
    assert '"query":"active"' in runtime.expressions[1]
    assert '"threadId":"thread-1"' in runtime.expressions[2]
    assert '"cursor":"cursor-1"' in runtime.expressions[2]
    assert '"includeOutputs":true' in runtime.expressions[2]
    assert '"maxOutputCharsPerItem":120' in runtime.expressions[2]
    assert '"turnLimit":4' in runtime.expressions[2]
    assert "thread_id" not in runtime.expressions[2]
    assert "max_output_chars_per_item" not in runtime.expressions[2]


def test_connect_is_idempotent_and_context_manager_closes_runtime() -> None:
    runtime = FakeRuntime(responses=[discovery_result(ALL_CODEX_APP_THREAD_TOOL_NAMES)])
    client = client_with_runtime(runtime)

    async def run_client() -> None:
        async with client as connected:
            assert connected is client
            assert await client.connect() is client
            assert client.target is not None
            assert client.tool_discovery is not None

    asyncio.run(run_client())

    assert runtime.closed
    assert len(runtime.expressions) == 1


def test_close_without_runtime_is_noop() -> None:
    asyncio.run(CodexAppCdpClient().close())


def test_client_uses_settings_for_target_selection_and_timeouts() -> None:
    runtime = FakeRuntime(responses=[discovery_result(ALL_CODEX_APP_THREAD_TOOL_NAMES)])
    settings = CodexAppCdpSettings(
        endpoint="http://settings",
        target_url="app://custom/index.html",
        target_url_prefix="app://custom/",
        http_timeout=1.25,
        runtime_timeout=2.5,
    )

    async def target_fetcher(received_settings: CodexAppCdpSettings) -> tuple[CdpTarget, ...]:
        await asyncio.sleep(0)
        assert received_settings is settings
        return (
            CdpTarget(
                id="fallback",
                kind="page",
                url="app://custom/other.html",
                websocket_debugger_url="ws://fallback",
            ),
            CdpTarget(
                id="exact",
                kind="page",
                url="app://custom/index.html",
                websocket_debugger_url="ws://exact",
            ),
        )

    async def runtime_connector(
        websocket_url: str,
        *,
        runtime_timeout: float,
    ) -> CdpRuntimeEvaluator:
        await asyncio.sleep(0)
        assert websocket_url == "ws://exact"
        assert runtime_timeout == pytest.approx(2.5)
        return runtime

    client = CodexAppCdpClient(
        settings=settings,
        target_fetcher=target_fetcher,
        runtime_connector=runtime_connector,
    )

    asyncio.run(client.connect())

    assert client.target is not None
    assert client.target.id == "exact"


def test_client_default_connector_uses_keyword_runtime_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = FakeWebSocket(
        incoming=[
            json.dumps(
                {
                    "id": 1,
                    "result": {
                        "result": {
                            "value": discovery_result(ALL_CODEX_APP_THREAD_TOOL_NAMES),
                        },
                    },
                },
            ),
        ],
    )
    settings = CodexAppCdpSettings(endpoint="http://cdp", runtime_timeout=0.125)

    class FakeWebsocketsModule:
        @staticmethod
        async def connect(uri: str, *, max_size: int | None) -> FakeWebSocket:
            await asyncio.sleep(0)
            assert uri == "ws://target"
            assert max_size is None
            return websocket

    async def target_fetcher(received_settings: CodexAppCdpSettings) -> tuple[CdpTarget, ...]:
        await asyncio.sleep(0)
        assert received_settings is settings
        return (
            CdpTarget(
                id="target",
                kind="page",
                url="app://-/index.html",
                websocket_debugger_url="ws://target",
            ),
        )

    monkeypatch.setattr(cdp_runtime, "import_module", lambda _name: FakeWebsocketsModule())
    client = CodexAppCdpClient(settings=settings, target_fetcher=target_fetcher)

    asyncio.run(client.connect())

    assert client._runtime is not None
    assert client._runtime._timeout == pytest.approx(0.125)


def test_wrapper_rejects_missing_discovered_tool() -> None:
    runtime = FakeRuntime(responses=[discovery_result(("list_threads", "read_thread"))])
    client = client_with_runtime(runtime)

    async def run_client() -> None:
        await client.connect()
        with pytest.raises(CodexAppCdpDiscoveryError, match="set_thread_pinned"):
            await client.set_thread_pinned(
                thread_id="thread-1",
                pinned=True,
            )

    asyncio.run(run_client())


def test_invoke_tool_rejects_missing_runtime_after_connect() -> None:
    class BrokenClient(CodexAppCdpClient):
        async def connect(self) -> BrokenClient:
            await asyncio.sleep(0)
            return self

    async def run_client() -> None:
        client = BrokenClient()
        with pytest.raises(CodexAppCdpConnectionError, match="not connected"):
            await client._invoke_tool("list_threads", {})

    asyncio.run(run_client())


def test_mutating_wrappers_translate_to_renderer_payloads() -> None:
    runtime = FakeRuntime(
        responses=[
            discovery_result(ALL_CODEX_APP_THREAD_TOOL_NAMES),
            renderer_success({"threadId": "thread-created"}),
            renderer_success({"threadId": "thread-1"}),
            renderer_success(
                {
                    "environment": {"type": "same-directory"},
                    "sourceThreadId": "thread-1",
                    "threadId": "thread-2",
                    "continuation": "Continue only if needed.",
                },
            ),
            renderer_success({"threadId": "thread-1", "pinned": True}),
            renderer_success({"threadId": "thread-1", "archived": False}),
            renderer_success({"threadId": "thread-1", "title": "New title"}),
            renderer_success(
                {
                    "destinationHostDisplayName": "Local",
                    "threadId": "thread-2",
                    "threadTitle": "Thread title",
                },
            ),
        ],
    )
    client = client_with_runtime(runtime)

    async def run_client() -> None:
        await client.connect()
        create_result = await client.create_thread(
            prompt="start",
            target={"type": "projectless"},
        )
        send_result = await client.send_message_to_thread(
            thread_id="thread-1",
            prompt="continue",
            model="gpt-5.5",
            thinking="medium",
        )
        fork_result = await client.fork_thread(
            thread_id="thread-1",
            environment={"type": "same-directory"},
        )
        pinned_result = await client.set_thread_pinned(
            thread_id="thread-1",
            pinned=True,
        )
        archived_result = await client.set_thread_archived(
            thread_id="thread-1",
            archived=False,
        )
        title_result = await client.set_thread_title(
            thread_id="thread-1",
            title="New title",
        )
        handoff_result = await client.handoff_thread(
            thread_id="thread-1",
            destination_host_id="local",
        )
        assert create_result.model_dump() == {
            "thread_id": "thread-created",
            "pending_worktree_id": None,
            "projectless_output_directory": None,
        }
        assert send_result.model_dump() == {"thread_id": "thread-1"}
        assert fork_result.model_dump() == {
            "environment": {"type": "same-directory"},
            "source_thread_id": "thread-1",
            "thread_id": "thread-2",
            "pending_worktree_id": None,
            "continuation": "Continue only if needed.",
        }
        assert pinned_result.model_dump() == {"thread_id": "thread-1", "pinned": True}
        assert archived_result.model_dump() == {"thread_id": "thread-1", "archived": False}
        assert title_result.model_dump() == {"thread_id": "thread-1", "title": "New title"}
        assert handoff_result.model_dump() == {
            "destination_host_display_name": "Local",
            "thread_id": "thread-2",
            "thread_title": "Thread title",
        }

    asyncio.run(run_client())

    assert (
        '"create_thread", {"prompt":"start","target":{"type":"projectless"}}'
        in runtime.expressions[1]
    )
    assert '"threadId":"thread-1"' in runtime.expressions[2]
    assert '"prompt":"continue"' in runtime.expressions[2]
    assert '"model":"gpt-5.5"' in runtime.expressions[2]
    assert '"thinking":"medium"' in runtime.expressions[2]
    assert '"environment":{"type":"same-directory"}' in runtime.expressions[3]
    assert '"pinned":true' in runtime.expressions[4]
    assert '"archived":false' in runtime.expressions[5]
    assert '"title":"New title"' in runtime.expressions[6]
    assert '"destinationHostId":"local"' in runtime.expressions[7]
    assert "destination_host_id" not in runtime.expressions[7]
