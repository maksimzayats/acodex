from __future__ import annotations

import os
import sys
from pathlib import Path
from textwrap import dedent


def create_fake_codex_executable(tmp_path: Path) -> Path:
    target = tmp_path / "fake_codex_target.py"
    target.write_text(_SCRIPT, encoding="utf-8")

    if os.name == "nt":
        executable = tmp_path / "codex.bat"
        executable.write_text(
            f'@echo off\r\n"{sys.executable}" "{target}" %*\r\n',
            encoding="utf-8",
        )
        return executable

    executable = tmp_path / "codex"
    executable.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{target}" "$@"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


_SCRIPT = dedent(
    """\
    from __future__ import annotations

    import json
    import os
    import sys
    from pathlib import Path


    def parse_args(argv: list[str]) -> tuple[list[str], str | None, str | None]:
        images: list[str] = []
        output_schema: str | None = None
        resume_id: str | None = None
        index = 0
        while index < len(argv):
            current = argv[index]
            if current == "--image" and index + 1 < len(argv):
                images.append(argv[index + 1])
                index += 2
                continue
            if current == "--output-schema" and index + 1 < len(argv):
                output_schema = argv[index + 1]
                index += 2
                continue
            if current == "resume" and index + 1 < len(argv):
                resume_id = argv[index + 1]
                index += 2
                continue
            index += 1
        return images, output_schema, resume_id


    def emit(payload: dict[str, object]) -> None:
        sys.stdout.write(json.dumps(payload) + "\\n")
        sys.stdout.flush()


    argv = sys.argv[1:]
    stdin_text = sys.stdin.read()
    mode = os.environ.get("FAKE_CODEX_MODE", "lines")
    images, output_schema, resume_id = parse_args(argv)

    if mode == "lines":
        lines = json.loads(os.environ.get("FAKE_LINES_JSON", '["line-1", "line-2"]'))
        for line in lines:
            sys.stdout.write(str(line) + "\\n")
        sys.stdout.flush()
        raise SystemExit(0)

    if mode == "env_guard":
        marker_name = os.environ.get("FAKE_MARKER_NAME", "SHOULD_NOT_LEAK")
        leaked = marker_name in os.environ
        sys.stdout.write(("leaked" if leaked else "clean") + "\\n")
        sys.stdout.flush()
        raise SystemExit(0)

    if mode == "thread_success":
        thread_id = os.environ.get("FAKE_THREAD_ID", "thread-from-fake")
        responses = json.loads(os.environ.get("FAKE_RESPONSES_JSON", '["first", "second"]'))
        emit({"type": "thread.started", "thread_id": thread_id})
        emit({"type": "turn.started"})
        for index, text in enumerate(responses):
            emit(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "id": f"item-{index}",
                        "text": str(text),
                    },
                },
            )
        emit(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 5,
                },
            },
        )
        raise SystemExit(0)

    if mode == "thread_failed":
        message = os.environ.get("FAKE_FAILURE_MESSAGE", "failure from fake codex")
        emit({"type": "thread.started", "thread_id": "thread-failed"})
        emit({"type": "turn.started"})
        emit({"type": "turn.failed", "error": {"message": message}})
        raise SystemExit(0)

    if mode == "normalize_capture":
        payload = {
            "stdin": stdin_text,
            "images": images,
            "resume_id": resume_id,
            "argv": argv,
        }
        emit({"type": "thread.started", "thread_id": "thread-normalize"})
        emit(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "id": "capture",
                    "text": json.dumps(payload),
                },
            },
        )
        emit(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
            },
        )
        raise SystemExit(0)

    if mode == "schema_check":
        schema_exists = False
        schema_payload: object = None
        if output_schema is not None:
            schema_path = Path(output_schema)
            schema_exists = schema_path.exists()
            if schema_exists:
                schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
        emit({"type": "thread.started", "thread_id": "thread-schema"})
        emit(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "id": "schema",
                    "text": json.dumps(
                        {
                            "schema_path": output_schema,
                            "schema_exists": schema_exists,
                            "schema_payload": schema_payload,
                        },
                    ),
                },
            },
        )
        emit(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 2,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
            },
        )
        raise SystemExit(0)

    raise SystemExit(0)
    """,
)
