from __future__ import annotations

from acodex.types.exec import CodexExecArg, CodexExecArgs


def test_exec_arg_enum_matches_typed_dict() -> None:
    typed_dict_annotation = dict(CodexExecArgs.__annotations__)

    for arg in CodexExecArg:
        typed_dict_annotation.pop(arg.value)

    # check that all enum values are present in the typed dict and that there are no extra keys in the typed dict
    assert typed_dict_annotation == {}
