from __future__ import annotations

from typing import cast

import pytest

from acodex._internal.toml import to_toml_value
from acodex.types.codex_options import CodexConfigValue


def test_to_toml_value_renders_string_like_json_stringify() -> None:
    assert to_toml_value("hello", "value") == '"hello"'
    assert to_toml_value("привет", "value") == '"привет"'


def test_to_toml_value_renders_numbers_and_booleans() -> None:
    true_value = True
    false_value = False

    assert to_toml_value(42, "value") == "42"
    assert to_toml_value(1.5, "value") == "1.5"
    assert to_toml_value(1.0, "value") == "1"
    assert to_toml_value(true_value, "value") == "true"
    assert to_toml_value(false_value, "value") == "false"


def test_to_toml_value_renders_numbers_with_js_stringification_rules() -> None:
    assert to_toml_value(-0.0, "value") == "0"
    assert to_toml_value(1e-7, "value") == "1e-7"
    assert to_toml_value(1e-6, "value") == "0.000001"
    assert to_toml_value(1e16, "value") == "10000000000000000"
    assert to_toml_value(1e21, "value") == "1e+21"


def test_to_toml_value_renders_int_with_js_number_parity() -> None:
    assert to_toml_value(cast("CodexConfigValue", 9007199254740993), "value") == "9007199254740992"


def test_to_toml_value_renders_nested_array_and_object() -> None:
    value: CodexConfigValue = {
        "plain": "value",
        "needs.dot": {"nested-key": [1, True, "x"]},
    }
    assert (
        to_toml_value(value, "value")
        == '{plain = "value", "needs.dot" = {nested-key = [1, true, "x"]}}'
    )


def test_to_toml_value_rejects_non_finite_number() -> None:
    with pytest.raises(ValueError, match="Codex config override at value must be a finite number"):
        to_toml_value(float("inf"), "value")


def test_to_toml_value_rejects_overflow_int_as_non_finite_number() -> None:
    with pytest.raises(ValueError, match="Codex config override at value must be a finite number"):
        to_toml_value(cast("CodexConfigValue", 10**400), "value")


def test_to_toml_value_rejects_null_value_with_path() -> None:
    value = cast("CodexConfigValue", {"root": None})
    with pytest.raises(ValueError, match=r"Codex config override at value\.root cannot be null"):
        to_toml_value(value, "value")


def test_to_toml_value_rejects_empty_or_non_string_keys() -> None:
    with pytest.raises(ValueError, match="Codex config override keys must be non-empty strings"):
        to_toml_value({"": 1}, "value")

    with pytest.raises(ValueError, match="Codex config override keys must be non-empty strings"):
        to_toml_value(cast("CodexConfigValue", {1: "x"}), "value")


def test_to_toml_value_rejects_unsupported_value_type() -> None:
    value = cast("CodexConfigValue", (1, 2))
    with pytest.raises(
        ValueError,
        match=r"Unsupported Codex config override value at value: tuple",
    ):
        to_toml_value(value, "value")
