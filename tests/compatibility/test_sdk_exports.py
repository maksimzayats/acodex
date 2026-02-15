from acodex import __all__ as acodex_all
from tests.config import ROOT_DIR
from tools.compatibility.get_ts_exports import extract_exported_objects


def test_same_exports() -> None:
    ts_sdk_root = ROOT_DIR / "_ts_sdk" / "src" / "index.ts"

    exported_from_ts = set(extract_exported_objects(ts_sdk_root.read_text()))
    exported_from_python = set(acodex_all)

    diff = exported_from_ts - exported_from_python
