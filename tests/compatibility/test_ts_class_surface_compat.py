from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import get_type_hints

from acodex.codex import AsyncCodex, Codex
from acodex.thread import AsyncThread, Thread
from tests.compatibility._assertions import camel_to_snake
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.ts_class_parser import extract_exported_class_members


def test_codex_class_surface_supports_typescript_methods() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "codex.ts").read_text(encoding="utf-8")
    surface = extract_exported_class_members(ts_source, "Codex")

    ts_methods = {camel_to_snake(name) for name in surface.methods}
    assert {"start_thread", "resume_thread"} <= ts_methods, (
        f"Unexpected TS Codex methods: {sorted(ts_methods)}"
    )

    for method_name in ts_methods:
        assert hasattr(Codex, method_name), f"Codex missing method: {method_name}"
        assert hasattr(AsyncCodex, method_name), f"AsyncCodex missing method: {method_name}"

    _assert_no_required_args(Codex.start_thread, expected_name="start_thread")
    _assert_one_required_positional(
        Codex.resume_thread,
        expected_name="resume_thread",
        arg_name="thread_id",
    )


def test_thread_class_surface_supports_typescript_members() -> None:
    ts_source = (VENDOR_TS_SDK_SRC / "thread.ts").read_text(encoding="utf-8")
    surface = extract_exported_class_members(ts_source, "Thread")

    ts_methods = {camel_to_snake(name) for name in surface.methods}
    ts_getters = {camel_to_snake(name) for name in surface.getters}

    assert {"run", "run_streamed"} <= ts_methods, (
        f"Unexpected TS Thread methods: {sorted(ts_methods)}"
    )
    assert {"id"} <= ts_getters, f"Unexpected TS Thread getters: {sorted(ts_getters)}"

    for method_name in ts_methods:
        assert hasattr(Thread, method_name), f"Thread missing method: {method_name}"
        assert hasattr(AsyncThread, method_name), f"AsyncThread missing method: {method_name}"

    thread_id = inspect.getattr_static(Thread, "id")
    async_thread_id = inspect.getattr_static(AsyncThread, "id")
    assert isinstance(thread_id, property), "Thread.id must be a property"
    assert isinstance(async_thread_id, property), "AsyncThread.id must be a property"
    assert thread_id.fget is not None
    assert async_thread_id.fget is not None
    assert get_type_hints(thread_id.fget, include_extras=True)["return"] == str | None
    assert get_type_hints(async_thread_id.fget, include_extras=True)["return"] == str | None

    _assert_one_required_positional(Thread.run, expected_name="run", arg_name="input")
    _assert_one_required_positional(
        Thread.run_streamed,
        expected_name="run_streamed",
        arg_name="input",
    )
    _assert_optional_parameter(Thread.run, expected_name="run", arg_name="output_type")
    _assert_optional_parameter(
        Thread.run_streamed,
        expected_name="run_streamed",
        arg_name="output_type",
    )

    assert inspect.iscoroutinefunction(AsyncThread.run), "AsyncThread.run must be async"
    assert inspect.iscoroutinefunction(AsyncThread.run_streamed), (
        "AsyncThread.run_streamed must be async"
    )
    _assert_optional_parameter(AsyncThread.run, expected_name="run", arg_name="output_type")
    _assert_optional_parameter(
        AsyncThread.run_streamed,
        expected_name="run_streamed",
        arg_name="output_type",
    )


def _assert_no_required_args(func: Callable[..., object], *, expected_name: str) -> None:
    signature = inspect.signature(func)
    params = list(signature.parameters.values())[1:]
    required = [param for param in params if _is_required(param)]
    assert not required, f"{expected_name} must not require args besides self: {required!r}"


def _assert_one_required_positional(
    func: Callable[..., object],
    *,
    expected_name: str,
    arg_name: str,
) -> None:
    signature = inspect.signature(func)
    params = list(signature.parameters.values())[1:]
    assert params, f"{expected_name} must accept parameters besides self"

    first = params[0]
    assert first.name == arg_name, (
        f"{expected_name} first arg must be {arg_name!r}, got {first.name!r}"
    )
    assert first.kind in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }, f"{expected_name}.{arg_name} must be positional"
    assert _is_required(first), f"{expected_name}.{arg_name} must be required"

    remaining_required = [param for param in params[1:] if _is_required(param)]
    assert not remaining_required, (
        f"{expected_name} must not require args beyond {arg_name!r}: {remaining_required!r}"
    )


def _assert_optional_parameter(
    func: Callable[..., object],
    *,
    expected_name: str,
    arg_name: str,
) -> None:
    signature = inspect.signature(func)
    params = list(signature.parameters.values())[1:]
    param = next((current for current in params if current.name == arg_name), None)
    assert param is not None, f"{expected_name} must define optional {arg_name!r}"
    assert param.kind in {
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }, f"{expected_name}.{arg_name} must be a standard parameter"
    assert not _is_required(param), f"{expected_name}.{arg_name} must be optional"
    assert param.default is None, f"{expected_name}.{arg_name} default must be None"


def _is_required(param: inspect.Parameter) -> bool:
    if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
        return False
    return param.default is inspect.Parameter.empty
