from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, get_type_hints

import pytest
from pydantic import ValidationError
from typing_extensions import Unpack

from acodex import CodexAppCdpProtocolError, JsonObject, JsonValue
from acodex.asyncio.tools import base as tools_base
from acodex.asyncio.tools.base import dump_tool_input, parse_tool_output
from acodex.asyncio.tools.create_thread import (
    CreateThreadTool,
    CreateThreadToolInput,
    CreateThreadToolOutput,
)
from acodex.asyncio.tools.fork_thread import (
    ForkThreadTool,
    ForkThreadToolInput,
    ForkThreadToolOutput,
)
from acodex.asyncio.tools.handoff_thread import (
    HandoffThreadTool,
    HandoffThreadToolInput,
    HandoffThreadToolOutput,
)
from acodex.asyncio.tools.list_threads import (
    ListThreadsTool,
    ListThreadsToolInput,
    ListThreadsToolOutput,
)
from acodex.asyncio.tools.read_thread import (
    ReadThreadTool,
    ReadThreadToolInput,
    ReadThreadToolOutput,
)
from acodex.asyncio.tools.send_message_to_thread import (
    SendMessageToThreadTool,
    SendMessageToThreadToolInput,
    SendMessageToThreadToolOutput,
)
from acodex.asyncio.tools.set_thread_archived import (
    SetThreadArchivedTool,
    SetThreadArchivedToolInput,
    SetThreadArchivedToolOutput,
)
from acodex.asyncio.tools.set_thread_pinned import (
    SetThreadPinnedTool,
    SetThreadPinnedToolInput,
    SetThreadPinnedToolOutput,
)
from acodex.asyncio.tools.set_thread_title import (
    SetThreadTitleTool,
    SetThreadTitleToolInput,
    SetThreadTitleToolOutput,
)
from acodex.asyncio.tools.thread_tools import CodexAppThreadTools

ToolCase = tuple[type, type, type, dict[str, Any], str | None, JsonObject, JsonObject, JsonObject]


def renderer_success(value: JsonValue) -> JsonObject:
    return {
        "contentItems": [{"type": "inputText", "text": json.dumps(value)}],
        "success": True,
    }


def renderer_failure(message: str) -> JsonObject:
    return {
        "contentItems": [{"type": "inputText", "text": message}],
        "success": False,
    }


def default_tool_result() -> JsonValue:
    return renderer_success({"threadId": "thread-1"})


@dataclass(slots=True)
class RecordingInvoker:
    result: JsonValue = field(default_factory=default_tool_result)
    calls: list[tuple[str, JsonObject, str | None]] = field(default_factory=list)

    async def __call__(
        self,
        tool_name: str,
        arguments: JsonObject,
        *,
        source_thread_id: str | None = None,
    ) -> JsonValue:
        self.calls.append((tool_name, arguments, source_thread_id))
        return self.result


LIST_THREADS_OUTPUT: JsonObject = {
    "schemaVersion": 1,
    "query": None,
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
    "page": {"order": "newest_first", "limit": 1, "nextCursor": None, "hasMore": False},
    "turns": [
        {
            "id": "turn-1",
            "status": "completed",
            "error": None,
            "startedAt": 11,
            "completedAt": 12,
            "durationMs": 100,
            "items": [
                {
                    "type": "userMessage",
                    "id": "item-1",
                    "content": [{"type": "text", "text": "hello"}],
                },
            ],
        },
    ],
}

TOOL_CASES: tuple[ToolCase, ...] = (
    (
        ListThreadsTool,
        ListThreadsToolInput,
        ListThreadsToolOutput,
        {"limit": 5},
        None,
        {"limit": 5},
        LIST_THREADS_OUTPUT,
        {
            "schema_version": 1,
            "query": None,
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
        },
    ),
    (
        ReadThreadTool,
        ReadThreadToolInput,
        ReadThreadToolOutput,
        {
            "thread_id": "thread-1",
            "cursor": "cursor-1",
            "include_outputs": True,
            "max_output_chars_per_item": 120,
            "turn_limit": 4,
        },
        None,
        {
            "threadId": "thread-1",
            "cursor": "cursor-1",
            "includeOutputs": True,
            "maxOutputCharsPerItem": 120,
            "turnLimit": 4,
        },
        READ_THREAD_OUTPUT,
        {
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
                "limit": 1,
                "next_cursor": None,
                "has_more": False,
            },
            "turns": [
                {
                    "id": "turn-1",
                    "status": "completed",
                    "error": None,
                    "started_at": 11,
                    "completed_at": 12,
                    "duration_ms": 100,
                    "items": [
                        {
                            "type": "userMessage",
                            "id": "item-1",
                            "content": [
                                {"type": "text", "text": "hello", "codex_delegation": None},
                            ],
                        },
                    ],
                },
            ],
        },
    ),
    (
        CreateThreadTool,
        CreateThreadToolInput,
        CreateThreadToolOutput,
        {"prompt": "start", "target": {"type": "projectless"}, "thinking": "medium"},
        None,
        {"prompt": "start", "target": {"type": "projectless"}, "thinking": "medium"},
        {"threadId": "thread-1", "projectlessOutputDirectory": "/repo/output/thread-1"},
        {
            "thread_id": "thread-1",
            "pending_worktree_id": None,
            "projectless_output_directory": "/repo/output/thread-1",
        },
    ),
    (
        SendMessageToThreadTool,
        SendMessageToThreadToolInput,
        SendMessageToThreadToolOutput,
        {"thread_id": "thread-1", "prompt": "continue", "model": "gpt-5.5"},
        None,
        {"threadId": "thread-1", "prompt": "continue", "model": "gpt-5.5"},
        {"threadId": "thread-1"},
        {"thread_id": "thread-1"},
    ),
    (
        ForkThreadTool,
        ForkThreadToolInput,
        ForkThreadToolOutput,
        {"thread_id": "thread-1", "environment": {"type": "same-directory"}},
        "source-thread",
        {"threadId": "thread-1", "environment": {"type": "same-directory"}},
        {
            "environment": {"type": "same-directory"},
            "sourceThreadId": "thread-1",
            "threadId": "thread-2",
            "continuation": "Continue only if needed.",
        },
        {
            "environment": {"type": "same-directory"},
            "source_thread_id": "thread-1",
            "thread_id": "thread-2",
            "pending_worktree_id": None,
            "continuation": "Continue only if needed.",
        },
    ),
    (
        SetThreadPinnedTool,
        SetThreadPinnedToolInput,
        SetThreadPinnedToolOutput,
        {"thread_id": "thread-1", "pinned": True},
        None,
        {"threadId": "thread-1", "pinned": True},
        {"threadId": "thread-1", "pinned": True},
        {"thread_id": "thread-1", "pinned": True},
    ),
    (
        SetThreadArchivedTool,
        SetThreadArchivedToolInput,
        SetThreadArchivedToolOutput,
        {"thread_id": "thread-1", "archived": False},
        None,
        {"threadId": "thread-1", "archived": False},
        {"threadId": "thread-1", "archived": False},
        {"thread_id": "thread-1", "archived": False},
    ),
    (
        SetThreadTitleTool,
        SetThreadTitleToolInput,
        SetThreadTitleToolOutput,
        {"thread_id": "thread-1", "title": "New title"},
        None,
        {"threadId": "thread-1", "title": "New title"},
        {"threadId": "thread-1", "title": "New title"},
        {"thread_id": "thread-1", "title": "New title"},
    ),
    (
        HandoffThreadTool,
        HandoffThreadToolInput,
        HandoffThreadToolOutput,
        {"thread_id": "thread-1", "destination_host_id": "local"},
        None,
        {"threadId": "thread-1", "destinationHostId": "local"},
        {
            "destinationHostDisplayName": "Local",
            "threadId": "thread-2",
            "threadTitle": "Thread title",
        },
        {
            "destination_host_display_name": "Local",
            "thread_id": "thread-2",
            "thread_title": "Thread title",
        },
    ),
)


@pytest.mark.parametrize("case", TOOL_CASES)
def test_tool_invocation_dumps_aliases_and_parses_output_model(case: ToolCase) -> None:
    (
        tool_type,
        input_type,
        output_type,
        arguments,
        source_thread_id,
        renderer_payload,
        output,
        expected_dump,
    ) = case
    invoker = RecordingInvoker(result=renderer_success(output))
    tool = tool_type(invoker)

    async def run_tool() -> Any:
        if source_thread_id is not None:
            return await tool(source_thread_id=source_thread_id, **arguments)
        return await tool(**arguments)

    result = asyncio.run(run_tool())

    assert isinstance(result, output_type)
    assert result.model_dump() == expected_dump
    assert invoker.calls == [(tool.NAME, renderer_payload, source_thread_id)]
    assert tool.INPUT_TYPE is input_type
    assert tool.OUTPUT_TYPE is output_type


@pytest.mark.parametrize(
    "case",
    [
        (ListThreadsToolInput, {"limit": 5, "query": None}, {"limit": 5}),
        (
            ForkThreadToolInput,
            {"thread_id": "thread-1", "environment": None},
            {"threadId": "thread-1"},
        ),
        (ForkThreadToolInput, {}, {}),
        (
            HandoffThreadToolInput,
            {"thread_id": "thread-1", "destination_host_id": None},
            {"threadId": "thread-1"},
        ),
    ],
)
def test_dump_tool_input_excludes_none_and_uses_optional_aliases(
    case: tuple[type, JsonObject, JsonObject],
) -> None:
    input_type, payload, expected = case
    assert dump_tool_input(input_type, payload) == expected


def test_read_thread_tool_input_and_signature_are_snake_case() -> None:
    type_hints = get_type_hints(ReadThreadTool.__call__, include_extras=True)
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


def test_fork_thread_source_context_is_not_renderer_payload() -> None:
    type_hints = get_type_hints(ForkThreadTool.__call__, include_extras=True)
    fork_thread_keys = ForkThreadToolInput.__annotations__.keys()

    assert type_hints["source_thread_id"] is str
    assert type_hints["arguments"] == Unpack[ForkThreadToolInput]
    assert "source_thread_id" not in fork_thread_keys
    assert "sourceThreadId" not in fork_thread_keys


def test_read_thread_output_covers_renderer_item_variants() -> None:
    output = deepcopy(READ_THREAD_OUTPUT)
    output["thread"] = {
        "id": "thread-1",
        "title": "Thread title",
        "preview": "Preview",
        "status": {"type": "active", "activeFlags": []},
        "cwd": "/repo",
        "createdAt": 10,
        "updatedAt": 20,
    }
    output["turns"] = [
        {
            "id": "turn-1",
            "status": "completed",
            "error": {"message": "failed", "additionalDetails": "details"},
            "startedAt": 11,
            "completedAt": 12,
            "durationMs": 100,
            "items": [
                {
                    "type": "userMessage",
                    "id": "user-1",
                    "content": [
                        {
                            "type": "text",
                            "text": "hello",
                            "codexDelegation": {
                                "sourceThreadId": "source-1",
                                "input": "delegated",
                            },
                        },
                        {"type": "image", "url": "https://example.test/image.png"},
                        {"type": "localImage", "path": "/repo/image.png"},
                        {"type": "skill", "name": "skill", "path": "/repo/skill"},
                        {"type": "mention", "name": "file", "path": "/repo/file"},
                    ],
                },
                {"type": "agentMessage", "id": "agent-1", "text": "answer", "phase": "final"},
                {"type": "plan", "id": "plan-1", "text": "plan"},
                {
                    "type": "reasoning",
                    "id": "reasoning-1",
                    "summary": "summary",
                    "content": [{"text": "hidden", "truncated": False}],
                },
                {
                    "type": "commandExecution",
                    "id": "cmd-1",
                    "command": "pwd",
                    "cwd": "/repo",
                    "status": "completed",
                    "exitCode": 0,
                    "durationMs": 5,
                    "output": {"text": "out", "truncated": True, "originalChars": 5},
                },
                {
                    "type": "fileChange",
                    "id": "file-1",
                    "status": "completed",
                    "changes": [
                        {
                            "path": "added.txt",
                            "kind": {"type": "add"},
                            "diff": {"text": "added", "truncated": False},
                        },
                        {
                            "path": "file.txt",
                            "kind": {"type": "update", "move_path": None},
                            "diff": {"text": "diff", "truncated": False},
                        },
                        {
                            "path": "deleted.txt",
                            "kind": {"type": "delete"},
                            "diff": {"text": "deleted", "truncated": False},
                        },
                    ],
                },
                {
                    "type": "mcpToolCall",
                    "id": "mcp-1",
                    "server": "server",
                    "tool": "tool",
                    "arguments": {"x": 1},
                    "status": "completed",
                    "durationMs": 4,
                },
                {
                    "type": "dynamicToolCall",
                    "id": "dyn-1",
                    "tool": "tool",
                    "arguments": {"x": 1},
                    "status": "completed",
                    "success": True,
                    "durationMs": 4,
                },
                {
                    "type": "collabAgentToolCall",
                    "id": "collab-1",
                    "tool": "send",
                    "status": "completed",
                    "senderThreadId": "sender",
                    "receiverThreadIds": ["receiver"],
                    "prompt": "prompt",
                    "model": "gpt-5.5",
                    "reasoningEffort": "medium",
                },
                {
                    "type": "subAgentActivity",
                    "id": "sub-1",
                    "kind": "created",
                    "agentThreadId": "agent",
                    "agentPath": "/repo/agent",
                },
                {"type": "webSearch", "id": "web-1", "query": "q", "action": "search"},
                {"type": "imageView", "id": "view-1", "path": "/repo/image.png"},
                {
                    "type": "imageGeneration",
                    "id": "gen-1",
                    "status": "completed",
                    "revisedPrompt": "prompt",
                    "result": {"url": "https://example.test/image.png"},
                    "savedPath": None,
                },
                {"type": "enteredReviewMode", "id": "review-1", "review": {"id": 1}},
                {"type": "exitedReviewMode", "id": "review-2", "review": {"id": 1}},
                {"type": "hookPrompt", "id": "hook-1", "fragmentCount": 2},
                {"type": "contextCompaction", "id": "compact-1"},
            ],
        },
    ]

    result = parse_tool_output(ReadThreadToolOutput, renderer_success(output))

    assert result.thread.status.type == "active"
    assert len(result.turns[0].items) == 17
    assert result.turns[0].error is not None
    assert result.turns[0].error.additional_details == "details"


def test_create_and_fork_outputs_support_pending_worktree_results() -> None:
    create_result = parse_tool_output(
        CreateThreadToolOutput,
        renderer_success({"pendingWorktreeId": "pending-1"}),
    )
    fork_result = parse_tool_output(
        ForkThreadToolOutput,
        renderer_success(
            {
                "environment": {"type": "worktree"},
                "sourceThreadId": "thread-1",
                "threadId": None,
                "pendingWorktreeId": "pending-2",
                "continuation": "Wait for pending worktree.",
            },
        ),
    )

    assert create_result.pending_worktree_id == "pending-1"
    assert fork_result.pending_worktree_id == "pending-2"
    assert fork_result.thread_id is None


def test_create_and_fork_outputs_require_created_or_pending_id() -> None:
    with pytest.raises(ValidationError, match="threadId or pendingWorktreeId"):
        parse_tool_output(CreateThreadToolOutput, renderer_success({}))
    with pytest.raises(ValidationError, match="threadId or pendingWorktreeId"):
        parse_tool_output(
            ForkThreadToolOutput,
            renderer_success(
                {
                    "environment": {"type": "same-directory"},
                    "sourceThreadId": "thread-1",
                    "continuation": "Continue only if needed.",
                },
            ),
        )


def test_dump_tool_input_rejects_camel_case_public_keys() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="threadId"):
        dump_tool_input(ReadThreadToolInput, {"threadId": "thread-1"})


def test_dump_tool_input_rejects_non_object_dump() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="JSON object"):
        dump_tool_input(str, "not an object")


def test_parse_tool_output_rejects_non_object_renderer_result() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="JSON object"):
        parse_tool_output(ListThreadsToolOutput, "not an object")


def test_parse_tool_output_rejects_failed_renderer_envelope() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="tool failed"):
        parse_tool_output(ListThreadsToolOutput, renderer_failure("tool failed"))


def test_parse_tool_output_rejects_empty_renderer_envelope() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="contentItems"):
        parse_tool_output(ListThreadsToolOutput, {"contentItems": [], "success": True})


def test_parse_tool_output_rejects_non_json_renderer_text() -> None:
    with pytest.raises(CodexAppCdpProtocolError, match="text must be JSON"):
        parse_tool_output(
            ListThreadsToolOutput,
            {"contentItems": [{"type": "inputText", "text": "not json"}], "success": True},
        )


def test_unknown_key_guard_ignores_non_mapping_annotations() -> None:
    bad_annotations = type("BadAnnotations", (), {"__annotations__": "not a mapping"})

    tools_base._reject_unknown_tool_input_keys(bad_annotations, {})


def test_thread_tool_binder_creates_one_bound_tool_per_renderer_tool() -> None:
    invoker = RecordingInvoker()
    tools = CodexAppThreadTools.bind(invoker)

    assert isinstance(tools.list_threads, ListThreadsTool)
    assert isinstance(tools.read_thread, ReadThreadTool)
    assert isinstance(tools.create_thread, CreateThreadTool)
    assert isinstance(tools.send_message_to_thread, SendMessageToThreadTool)
    assert isinstance(tools.fork_thread, ForkThreadTool)
    assert isinstance(tools.set_thread_pinned, SetThreadPinnedTool)
    assert isinstance(tools.set_thread_archived, SetThreadArchivedTool)
    assert isinstance(tools.set_thread_title, SetThreadTitleTool)
    assert isinstance(tools.handoff_thread, HandoffThreadTool)
