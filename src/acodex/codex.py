from __future__ import annotations

from typing import TYPE_CHECKING

from acodex.codex_options import CodexOptions

if TYPE_CHECKING:
    from typing import Unpack


class BaseCodex:
    def __init__(self, **options: Unpack[CodexOptions]) -> None:
        self._options = options


class Codex(BaseCodex):
    pass


class AsyncCodex(BaseCodex):
    pass
