from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeGuard

from acodex.exceptions import CodexOutputSchemaError
from acodex.types.turn_options import OutputSchemaInput


class _Unset:
    __slots__ = ()


UNSET: Final[_Unset] = _Unset()


@dataclass(frozen=True, slots=True)
class OutputSchemaFile:
    schema_path: str | None
    cleanup: Callable[[], None]


def create_output_schema_file(schema: OutputSchemaInput | _Unset = UNSET) -> OutputSchemaFile:
    if schema is UNSET:
        return OutputSchemaFile(schema_path=None, cleanup=_noop)

    raw_schema: object = schema
    if not _is_json_object(raw_schema):
        raise CodexOutputSchemaError("output_schema must be a plain JSON object")

    schema_object: OutputSchemaInput = raw_schema

    temp_dir = tempfile.mkdtemp(prefix="codex-output-schema-")
    temp_dir_path = Path(temp_dir)
    schema_path = temp_dir_path / "schema.json"

    def cleanup() -> None:
        with contextlib.suppress(Exception):
            shutil.rmtree(temp_dir_path)

    try:
        _write_schema_file(schema_path, schema_object)
    except BaseException:
        cleanup()
        raise

    return OutputSchemaFile(schema_path=str(schema_path), cleanup=cleanup)


def _noop() -> None:
    return None


def _is_json_object(value: object) -> TypeGuard[OutputSchemaInput]:
    return isinstance(value, dict)


def _write_schema_file(path: Path, schema: OutputSchemaInput) -> None:
    path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
