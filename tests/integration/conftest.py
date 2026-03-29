from __future__ import annotations

import os
from pathlib import Path
from shutil import which
from typing import Final

import pytest

RUN_REAL_INTEGRATION_ENV: Final[str] = "ACODEX_RUN_REAL_INTEGRATION"
REAL_MODEL_ENV: Final[str] = "ACODEX_REAL_MODEL"
DEFAULT_REAL_MODEL: Final[str] = "gpt-5.3-codex"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config

    run_enabled = os.getenv(RUN_REAL_INTEGRATION_ENV) == "1"
    codex_path = which("codex")

    for item in items:
        if "real_integration" not in item.keywords:
            continue

        if not run_enabled:
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        f"Set {RUN_REAL_INTEGRATION_ENV}=1 to run real Codex integration tests."
                    ),
                ),
            )
            continue

        if codex_path is None:
            item.add_marker(
                pytest.mark.skip(
                    reason="Real integration tests require `codex` to be available on PATH.",
                ),
            )


@pytest.fixture(scope="session")
def codex_path() -> str:
    path = which("codex")
    if path is None:
        pytest.skip("Real integration tests require `codex` to be available on PATH.")
    return path


@pytest.fixture(scope="session")
def real_model() -> str:
    return os.getenv(REAL_MODEL_ENV) or DEFAULT_REAL_MODEL


@pytest.fixture()
def real_working_directory(tmp_path: Path) -> Path:
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    (workdir / "README.txt").write_text("real integration workspace\n", encoding="utf-8")
    return workdir
