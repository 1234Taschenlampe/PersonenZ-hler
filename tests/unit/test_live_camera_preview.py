"""Camera preview selection must never require both camera streams."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication

from visitor_counter.application_service import DashboardSnapshot
from visitor_counter.desktop.live_preview import online_camera_sources
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
