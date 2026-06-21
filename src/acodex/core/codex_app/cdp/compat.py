from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from urllib import request as url_request


@dataclass(frozen=True, slots=True)
class UrlLibCompat:
    request: ModuleType


urllib = UrlLibCompat(request=url_request)
