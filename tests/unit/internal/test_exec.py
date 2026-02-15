from __future__ import annotations

from acodex._internal.exec import CodexExecArgs, CodexExecCLICommandBuilder
from acodex.types.thread_options import ThreadOptions


def test_exec_cli_command_builder_dont_miss_args() -> None:
    builder = CodexExecCLICommandBuilder(args=CodexExecArgs(input="hello world"))

    command = builder.build_command()
    assert command.argv[0] == "exec"
    assert command.stdin == "hello world"

    exec_args = set(CodexExecArgs.__annotations__)
    assert exec_args - set(builder._seen_args) == set()


def test_exec_args_include_thead_args() -> None:
    thead_args = set(CodexExecArgs.__annotations__)
    thread_options_args = set(ThreadOptions.__annotations__)

    assert thread_options_args.issubset(thead_args)
