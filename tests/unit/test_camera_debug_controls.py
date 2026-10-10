"""Regression tests for one-camera operation and independent AI switches."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from visitor_counter.configuration import AppConfig
from visitor_counter.desktop.live_preview import CameraPreviewPanel
from visitor_counter.desktop.pages import SettingsPage
from visitor_counter.identity_manager import GlobalIdentityManager
from visitor_counter.inference_pipeline import ProcessingPipeline
from visitor_counter import service as service_module


class _StubWorker:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float = 0) -> None:
        _ = timeout


def _service_without_hardware(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        service_module,
        "enforce_license",
        lambda *args, **kwargs: SimpleNamespace(
            license_id="test", online_checked=False
        ),
    )
    monkeypatch.setattr(
        service_module, "privacy_readiness_errors", lambda config: []
    )
    instance = service_module.VisitorCounterService.__new__(
        service_module.VisitorCounterService
    )
    instance.project_root = tmp_path
    instance.paths = SimpleNamespace(
        license_file=tmp_path / "license.json",
        license_public_key=tmp_path / "public.pem",
    )
    instance.config = AppConfig()
    instance.stop_event = Event()
    instance.stop_event.set()  # No main loop / hardware is required.
    instance.captures = [_StubWorker(), _StubWorker()]
    instance.pipeline = _StubWorker()
    return instance


def test_service_accepts_one_configured_camera(tmp_path: Path, monkeypatch) -> None:
    service = _service_without_hardware(tmp_path, monkeypatch)
    service.config.cameras["camera_1"].device = "rtsp://192.168.2.21/Preview_01_sub"
    service.config.cameras["camera_2"].device = None
    assert service.run() == 0
    assert service.pipeline.started
    assert all(worker.started for worker in service.captures)


def test_service_still_blocks_if_both_cameras_missing(tmp_path: Path, monkeypatch) -> None:
    service = _service_without_hardware(tmp_path, monkeypatch)
    for camera in service.config.cameras.values():
        camera.device = None
    assert service.run() == 3
    assert not service.pipeline.started


def test_disabled_yolo_never_calls_hailo_detector() -> None:
    pipeline = ProcessingPipeline.__new__(ProcessingPipeline)
    pipeline.config = AppConfig()
    pipeline.config.model.detector_enabled = False
    assert pipeline._detect(object()) == []


def test_disabled_reid_prevents_geometry_only_cross_camera_match() -> None:
    config = AppConfig()
    identity = GlobalIdentityManager(
        config.identity, cross_camera_matching=False
    )
    assert identity._match_existing("camera_2", object(), 15, 640, 480) is None


def test_preview_opt_in_is_off_by_default_and_does_not_open_rtsp() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    panel = CameraPreviewPanel()
    panel.update_cameras(
        [{"camera_id": "camera_1", "status": "ONLINE",
          "actual_fps": 15, "seconds_since_last_frame": 0.1}],
        {"camera_1": "rtsp://192.168.2.21/Preview_01_sub"},
    )
    assert not panel._readers
    assert "Datenschutz" in panel.summary.text()
    panel.shutdown()
    panel.close()


def test_settings_expose_independent_yolo_and_reid_switches() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    page = SettingsPage()
    config = AppConfig()
    page.set_config(config)
    assert page.detector_enabled.isChecked()
    assert page.reid_enabled.isChecked()
    page.detector_enabled.setChecked(False)
    page.reid_enabled.setChecked(False)
    emitted = []
    page.save_requested.connect(emitted.append)
    page._emit_save()
    assert emitted[0]["model.detector_enabled"] is False
    assert emitted[0]["model.reid_required"] is False
    page.close()
