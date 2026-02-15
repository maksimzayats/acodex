from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from acodex.turn_options import JsonObject

OUTPUT_SCHEMA_TYPE_ERROR_MESSAGE = "output_schema must be a plain JSON object"


@dataclass(frozen=True, slots=True)
class OutputSchemaFileHandle:
    schema_path: str | None
    _schema_dir: str | None

    def cleanup(self) -> None:
        if self._schema_dir is None:
            return
        shutil.rmtree(self._schema_dir, ignore_errors=True)

    async def acleanup(self) -> None:
        await asyncio.to_thread(self.cleanup)


def create_output_schema_file(schema: JsonObject | None) -> OutputSchemaFileHandle:
    if schema is None:
        return OutputSchemaFileHandle(schema_path=None, _schema_dir=None)

    if not isinstance(schema, dict):
        raise TypeError(OUTPUT_SCHEMA_TYPE_ERROR_MESSAGE)

    schema_json = json.dumps(schema)
    schema_dir = Path(tempfile.mkdtemp(prefix="codex-output-schema-"))
    schema_path = schema_dir / "schema.json"
    handle = OutputSchemaFileHandle(schema_path=str(schema_path), _schema_dir=str(schema_dir))

    try:
        schema_path.write_text(schema_json, encoding="utf-8")
    except OSError:
        handle.cleanup()
        raise

    return handle
