from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

CommandT = TypeVar("CommandT", bound=Callable[..., Any])


def runtime_typer_signature(command: CommandT) -> CommandT:
    """Replace postponed annotations with runtime Typer annotations."""
    signature = inspect.signature(command)
    annotations = get_type_hints(command, include_extras=True)
    runtime_parameters = [
        parameter.replace(annotation=annotations.get(parameter.name, parameter.annotation))
        for parameter in signature.parameters.values()
    ]
    command.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=runtime_parameters,
        return_annotation=annotations.get("return", signature.return_annotation),
    )
    return command
