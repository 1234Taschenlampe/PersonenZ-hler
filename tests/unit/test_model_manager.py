from __future__ import annotations

from pathlib import Path

import pytest

from visitor_counter.configuration import ModelConfig
from visitor_counter.model_manager import ModelManager, ModelUnavailableError


def test_missing_custom_hef_disables_detector(tmp_path: Path) -> None:
    manager = ModelManager(ModelConfig(), tmp_path)
    status = manager.status()
    assert not status.exists
    assert not status.using_fallback
    assert "YOLO26" in status.error_message
    with pytest.raises(ModelUnavailableError):
        manager.require_available()


def test_yolo11_path_is_not_accepted_as_fallback(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "yolo11x_hailo10h.hef").write_bytes(b"not a real target")
    config = ModelConfig(hef_path="models/yolo11x_hailo10h.hef")
    manager = ModelManager(config, tmp_path)
    status = manager.status()
    assert status.using_fallback
    with pytest.raises(ModelUnavailableError):
        manager.require_available()


def test_custom_hef_symlink_is_rejected(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    real = models / "real.hef"
    real.write_bytes(b"hef")
    link = models / "yolo26m_detection_hailo10h_640.hef"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink support unavailable")
    manager = ModelManager(ModelConfig(), tmp_path)
    status = manager.status()
    assert not status.exists
    with pytest.raises(ModelUnavailableError):
        manager.require_available()
