from __future__ import annotations

from acodex import __all__ as acodex_all
from tests.compatibility.vendor_ts_sdk import VENDOR_TS_SDK_SRC
from tools.compatibility.get_ts_exports import extract_exported_objects


def test_same_exports() -> None:
    ts_sdk_root = VENDOR_TS_SDK_SRC / "index.ts"

    exported_from_ts = set(extract_exported_objects(ts_sdk_root.read_text()))
    exported_from_python = set(acodex_all)

    assert exported_from_ts - exported_from_python == set(), (
        "Some exports are missing from Python SDK"
    )

    assert exported_from_python - exported_from_ts == {
        "AsyncCodex",
        "AsyncThread",
    }, "Some exports are missing from TypeScript SDK"
