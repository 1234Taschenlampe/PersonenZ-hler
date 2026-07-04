from __future__ import annotations

import json
from pathlib import Path


def test_split_manifest_schema() -> None:
    path = Path("training/dataset/split_manifest.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert isinstance(data["items"], list)
