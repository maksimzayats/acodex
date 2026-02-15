from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from acodex._internal import output_schema_file
from acodex.exceptions import CodexOutputSchemaError
from acodex.types.turn_options import OutputSchemaInput


def _set_temp_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    tempfile.tempdir = None


def test_unset_schema_returns_noop() -> None:
    schema_file = output_schema_file.create_output_schema_file()
    assert schema_file.schema_path is None
    schema_file.cleanup()


@pytest.mark.parametrize("invalid", [None, [], "x", 1])
def test_rejects_non_object_schema(invalid: Any) -> None:
    with pytest.raises(CodexOutputSchemaError, match="output_schema must be a plain JSON object"):
        output_schema_file.create_output_schema_file(invalid)


def test_writes_schema_json_and_cleanup_removes_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_temp_root(monkeypatch, tmp_path)

    schema: OutputSchemaInput = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    schema_file = output_schema_file.create_output_schema_file(schema)
    assert schema_file.schema_path is not None

    schema_path = Path(schema_file.schema_path)
    assert schema_path.exists()
    assert json.loads(schema_path.read_text(encoding="utf-8")) == schema

    schema_file.cleanup()
    assert not schema_path.exists()
    assert not schema_path.parent.exists()


def test_cleanup_suppresses_removal_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_temp_root(monkeypatch, tmp_path)

    schema: OutputSchemaInput = {"type": "object"}
    schema_file = output_schema_file.create_output_schema_file(schema)

    def boom(_: Path) -> None:
        raise OSError("boom")

    monkeypatch.setattr(shutil, "rmtree", boom)
    schema_file.cleanup()


def test_write_failure_triggers_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schema: OutputSchemaInput = {"type": "object"}

    temp_dir = tmp_path / "codex-output-schema-fixed"

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "codex-output-schema-"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return str(temp_dir)

    def fake_write_schema_file(_: Path, __: OutputSchemaInput) -> None:
        raise OSError("boom")

    monkeypatch.setattr(tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(output_schema_file, "_write_schema_file", fake_write_schema_file)

    with pytest.raises(OSError, match="boom"):
        output_schema_file.create_output_schema_file(schema)

    assert not temp_dir.exists()
