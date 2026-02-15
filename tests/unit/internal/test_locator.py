from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from acodex._internal.locator import find_codex_path
from acodex.exceptions import CodexExecutableNotFoundError
from acodex.exec import AsyncCodexExec, CodexExec


def test_find_codex_path_resolves_executable_from_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = _create_fake_codex_executable(monkeypatch, tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    found = find_codex_path()

    assert Path(found).resolve() == executable.resolve()


def test_find_codex_path_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")

    with pytest.raises(
        CodexExecutableNotFoundError,
        match=re.escape(
            'Could not locate "codex" on PATH. Install the Codex CLI or pass `codex_path_override`.',
        ),
    ) as error:
        find_codex_path()

    assert error.value.executable_name == "codex"


def test_exec_constructors_resolve_executable_path_from_locator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = _create_fake_codex_executable(monkeypatch, tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    sync_exec = CodexExec()
    async_exec = AsyncCodexExec()
    expected_path = str(executable)

    assert sync_exec._executable_path == expected_path
    assert async_exec._executable_path == expected_path


def test_exec_constructors_keep_explicit_executable_path_when_path_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    explicit_path = "explicit/path/to/codex"

    sync_exec = CodexExec(executable_path=explicit_path)
    async_exec = AsyncCodexExec(executable_path=explicit_path)

    assert sync_exec._executable_path == explicit_path
    assert async_exec._executable_path == explicit_path


def test_exec_constructors_treat_empty_string_as_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = _create_fake_codex_executable(monkeypatch, tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))

    sync_exec = CodexExec(executable_path="")
    async_exec = AsyncCodexExec(executable_path="")
    expected_path = str(executable)

    assert sync_exec._executable_path == expected_path
    assert async_exec._executable_path == expected_path


def _create_fake_codex_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    if os.name == "nt":
        monkeypatch.setenv("PATHEXT", ".EXE;.BAT;.CMD")
        executable = tmp_path / "codex.bat"
        executable.write_text("@echo off\r\nexit /B 0\r\n", encoding="utf-8")
        return executable

    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable
