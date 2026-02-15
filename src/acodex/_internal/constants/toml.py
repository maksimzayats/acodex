from __future__ import annotations

import re

TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
