from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.skipif(not Path("training/exports/yolo26x_person_640.onnx").exists(), reason="custom ONNX artifact not produced yet")
def test_custom_onnx_exists() -> None:
    assert Path("training/exports/yolo26x_person_640.onnx").stat().st_size > 0
