from __future__ import annotations

import json
from pathlib import Path


def test_hef_manifest_declares_hailo10h() -> None:
    data = json.loads(Path("training/hailo/model_manifest.json").read_text(encoding="utf-8"))
    assert data["target_architecture"] == "HAILO10H"
    assert data["class_names"] == ["person"]
