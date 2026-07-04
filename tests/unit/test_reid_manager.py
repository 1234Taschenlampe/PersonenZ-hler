from __future__ import annotations

from pathlib import Path

import pytest

from visitor_counter.configuration import ModelConfig
from visitor_counter.model_manager import ModelUnavailableError
from visitor_counter.reid_manager import OSNetReIDManager


def test_missing_osnet_hef_blocks_reid(tmp_path: Path) -> None:
    manager = OSNetReIDManager(ModelConfig(), tmp_path)
    status = manager.status()
    assert not status.exists
    assert not status.ready
    assert "OSNet" in status.message
    with pytest.raises(ModelUnavailableError):
        manager.require_available(validate_hailo=False)


def test_osnet_hef_status_reports_sha(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    hef = models / "osnet_x1_0_hailo10h.hef"
    hef.write_bytes(b"osnet")
    manager = OSNetReIDManager(ModelConfig(), tmp_path)
    status = manager.status(validate_hailo=False)
    assert status.ready
    assert status.sha256 == "818e780efa3b6c5dbffdb472297db57bcf1a0da650a79083c01ad119e9f129ad"


def test_osnet_symlink_is_rejected(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    real = models / "real.hef"
    real.write_bytes(b"osnet")
    link = models / "osnet_x1_0_hailo10h.hef"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink support unavailable")
    manager = OSNetReIDManager(ModelConfig(), tmp_path)
    status = manager.status(validate_hailo=False)
    assert not status.ready


def test_fake_osnet_hef_fails_hailo_validation(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "osnet_x1_0_hailo10h.hef").write_bytes(b"not a real hef")
    manager = OSNetReIDManager(ModelConfig(), tmp_path)
    status = manager.status(validate_hailo=True)
    assert not status.ready
    assert "HailoRT" in status.message or "hailo_platform" in status.message
