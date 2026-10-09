"""Offscreen GUI integration tests for camera setup and honest RTSP status."""
from __future__ import annotations

import os
from time import time

import pytest
from PySide6.QtWidgets import QApplication

from visitor_counter.application_service import DashboardSnapshot
from visitor_counter.configuration import AppConfig
from visitor_counter.desktop.pages import CamerasPage
from visitor_counter.network_camera_discovery import RtspCandidate


@pytest.fixture
def app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance  # type: ignore[return-value]


def test_no_usb_webcams_does_not_reset_existing_rtsp_source(app: QApplication) -> None:
    page = CamerasPage()
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://admin:secret@192.168.1.11:554/Preview_01_sub"
    page.set_config(config)
    saved = page._source(page.cards["camera_1"]["source"])
    page.set_discovered([])
    assert page._source(page.cards["camera_1"]["source"]) == saved
    assert "USB" in page.discovery_status.text()
    assert "unabhängig" in page.discovery_status.text()


def test_discovery_does_not_replace_stored_source_and_fills_ip(app: QApplication) -> None:
    page = CamerasPage()
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://admin:secret@192.168.1.11:554/Preview_01_sub"
    page.set_config(config)
    page.set_discovered_network([
        RtspCandidate("192.168.1.12", 8554),
        RtspCandidate("192.168.1.13", 554, "ONVIF", False),
    ])
    combo = page.cards["camera_1"]["source"]
    assert page._source(combo) == config.cameras["camera_1"].device
    assert "nur ONVIF" in page.discovery_status.text()
    idx = next(i for i in range(combo.count()) if "192.168.1.12" in str(combo.itemData(i)))
    combo.setCurrentIndex(idx)
    assert page.cards["camera_1"]["ip_address"].text() == "192.168.1.12"
    assert page.cards["camera_1"]["rtsp_port"].value() == 8554


def test_stream_change_reuses_existing_secret_without_displaying_it(app: QApplication) -> None:
    page = CamerasPage()
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://admin:se%40cret@192.168.1.11:554/Preview_01_sub"
    page.set_config(config)
    c = page.cards["camera_1"]
    c["stream"].setCurrentIndex(1)
    page._apply_reolink("camera_1")
    source = page._source(c["source"])
    assert "admin:se%40cret@" in source
    assert source.endswith("_main")
    assert "se@cret" not in c["camera_password"].text()
    assert "se%40cret" not in c["source"].currentText()


def test_both_doors_accept_bidirectional_mapping_in_save_signal(app: QApplication) -> None:
    page = CamerasPage()
    page.set_config(AppConfig())
    saved = []
    page.save_requested.connect(saved.append)
    for cid in ("camera_1", "camera_2"):
        controls = page.cards[cid]
        controls["entry_direction"].setCurrentIndex(1)
    page._emit_save()
    assert saved
    for conf in saved[0].values():
        assert conf["entry_direction"] == "B_to_A"
        assert conf["exit_direction"] == "A_to_B"
        assert conf["counting_mode"] == "line"


def test_video_source_status_distinguishes_live_and_stale_streams(app: QApplication) -> None:
    page = CamerasPage()
    c = AppConfig()
    c.cameras["camera_1"].device = "rtsp://192.168.1.11/stream"
    c.cameras["camera_2"].device = "rtsp://192.168.1.12/stream"
    page.set_config(c)
    page.update_snapshot(DashboardSnapshot(
        timestamp=time(),
        cameras=[
            {"camera_id": "camera_1", "status": "ONLINE", "actual_fps": 10.0,
             "seconds_since_last_frame": 0.1},
            {"camera_id": "camera_2", "status": "RECONNECTING", "actual_fps": 0.0,
             "last_error": "RTSP-Stream liefert keine Bilder"},
        ],
    ))
    assert "2 konfigurierte" in page.cameras_summary.text()
    assert "1 von 2" in page.cameras_summary.text()
