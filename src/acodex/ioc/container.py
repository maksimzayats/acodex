from __future__ import annotations

from functools import cache

from diwire import Container


@cache
def get_container() -> Container:
    container = Container()

    _register_dependencies(container)

    return container


def _register_dependencies(container: Container) -> None:
    pass
