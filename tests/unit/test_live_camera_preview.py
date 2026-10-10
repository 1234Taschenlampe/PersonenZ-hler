"""Camera preview selection must never require both camera streams."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from visitor_counter.application_service import DashboardSnapshot
from visitor_counter.desktop.live_preview import online_camera_sources, preview_camera_source
from visitor_counter.desktop.pages import OverviewPage


def test_one_online_camera_is_enough_for_preview() -> None:
    cameras = [
        {"camera_id": "camera_1", "name": "Entrance", "status": "RECONNECTING",
         "actual_fps": 0, "seconds_since_last_frame": 20},
        {"camera_id": "camera_2", "name": "Exit", "status": "ONLINE",
         "actual_fps": 10.1, "seconds_since_last_frame": 0.2},
    ]
    sources = {"camera_1": "rtsp://127.0.0.1/1", "camera_2": "rtsp://127.0.0.1/2"}
    assert online_camera_sources(cameras, sources) == [
        ("camera_2", "Exit", "rtsp://127.0.0.1/2")
    ]


def test_reolink_preview_uses_substream_without_changing_login_or_query() -> None:
    source = "rtsp://fake:fixture@192.168.1.11:554/h264Preview_01_main?channel=1"
    assert preview_camera_source(source) == "rtsp://fake:fixture@192.168.1.11:554/h264Preview_01_sub?channel=1"
    other = "rtsp://192.168.1.12/custom-stream"
    assert preview_camera_source(other) == other


def test_preview_filters_stale_or_unconfigured_cameras_and_supports_more_than_two() -> None:
    cameras = [
        {"camera_id": "a", "status": "ONLINE", "actual_fps": 8,
         "seconds_since_last_frame": 0.3},
        {"camera_id": "b", "status": "ONLINE", "actual_fps": 8,
         "seconds_since_last_frame": 10.0},
        {"camera_id": "c", "status": "ONLINE", "actual_fps": 8,
         "seconds_since_last_frame": 0.3},
        {"camera_id": "d", "status": "ONLINE", "actual_fps": 0,
         "seconds_since_last_frame": 0.2},
    ]
    sources = {"a": "rtsp://127.0.0.1/a", "b": "rtsp://127.0.0.1/b",
               "c": "rtsp://127.0.0.1/c"}
    assert [row[0] for row in online_camera_sources(cameras, sources)] == ["a", "c"]
    assert online_camera_sources(cameras, {}) == []


def test_overview_does_not_require_every_camera_to_be_online() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    page = OverviewPage()
    page.update_snapshot(DashboardSnapshot(
        timestamp=0,
        cameras=[
            {"camera_id": "camera_1", "status": "OFFLINE"},
            {"camera_id": "camera_2", "status": "ONLINE", "actual_fps": 10,
             "seconds_since_last_frame": 0.2},
        ],
        runtime={"inference_fps": 12.3, "hailo_status": "ready"},
    ))
    assert page.health["Kameras"].text() == "1 von 2 online"
    assert "12.3 Bilder/s" in page.inference_info.text()
    page.close()


def test_overview_explains_online_camera_with_blocked_counting() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    page = OverviewPage()
    page.update_snapshot(DashboardSnapshot(
        timestamp=0,
        cameras=[{"camera_id": "camera_1", "name": "Eingang", "status": "ONLINE", "obstructed": True}],
        runtime={"detector_active": True, "inference_fps": 8},
    ))
    assert "blockiert die Zählung für: Eingang" in page.inference_info.text()
    page.close()
