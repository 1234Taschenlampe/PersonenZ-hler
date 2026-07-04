from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from visitor_counter.configuration import load_config
from visitor_counter.reid_manager import OSNetReIDManager
from visitor_counter.types import BoundingBox

@pytest.mark.hardware
def test_hailortcli_present() -> None:
    assert shutil.which("hailortcli"), "hailortcli is required on the Raspberry Pi"


@pytest.mark.hardware
def test_two_video_devices_present() -> None:
    devices = list(Path("/dev").glob("video*"))
    assert len(devices) >= 2, "two camera devices are required"


@pytest.mark.hardware
def test_runtime_config_requires_yolo26m_detection_and_disables_fallback() -> None:
    config = Path("config/config.yaml").read_text(encoding="utf-8")
    assert "require_custom_yolo26m: true" in config
    assert "detector_fallback_enabled: false" in config
    assert "hef_path: models/yolo26m_detection_hailo10h_640.hef" in config
    assert "postprocess_onnx_path: models/yolo26m_postprocessing.onnx" in config


@pytest.mark.hardware
def test_yolo26m_detection_hef_is_regular_when_available() -> None:
    target = Path("models/yolo26m_detection_hailo10h_640.hef")
    if not target.exists():
        pytest.skip("YOLO26m COCO HAILO10H detection HEF not deployed yet")
    assert target.is_file() and not target.is_symlink(), "YOLO26m detection HEF must be a regular file"
    assert target.stat().st_size > 0, "YOLO26m detection HEF must not be empty"


@pytest.mark.hardware
def test_osnet_reid_hef_is_regular_when_available() -> None:
    target = Path("models/osnet_x1_0_hailo10h.hef")
    if not target.exists():
        pytest.skip("OSNet x1.0 HAILO10H HEF not deployed yet")
    assert target.is_file() and not target.is_symlink(), "OSNet HEF must be a regular file"
    assert target.stat().st_size > 0, "OSNet HEF must not be empty"


@pytest.mark.hardware
def test_osnet_reid_runs_hailo_inference() -> None:
    config = load_config(Path("config/config.yaml"))
    manager = OSNetReIDManager(config.model, Path.cwd())
    manager.initialize()
    try:
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        image[100:500, 300:600] = 127
        embedding = manager.infer_embedding(image, BoundingBox(300, 100, 600, 500))
    finally:
        manager.close()
    assert embedding is not None
    assert len(embedding) == 512
    assert abs(sum(value * value for value in embedding) ** 0.5 - 1.0) < 1e-4


@pytest.mark.hardware
def test_pose_hef_is_not_configured_detection_fallback() -> None:
    forbidden = Path("models/yolo26m_pose_hailo10h_640.hef")
    config = Path("config/config.yaml").read_text(encoding="utf-8")
    active_model_section = config.split("tracking:", 1)[0]
    assert f"hef_path: {forbidden}" not in active_model_section


@pytest.mark.hardware
def test_yolo11x_is_manual_rollback_only_when_present() -> None:
    config = Path("config/config.yaml").read_text(encoding="utf-8")
    assert "models/yolo11x_hailo10h.hef" not in config.split("detector_candidates:", 1)[0]
