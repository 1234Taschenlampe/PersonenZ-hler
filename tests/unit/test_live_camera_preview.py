"""Camera preview selection must never require both camera streams."""
from __future__ import annotations

import os
import json
from pathlib import Path
from time import time
from threading import Timer

import cv2
import numpy as np
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt

from visitor_counter.application_service import DashboardSnapshot
from visitor_counter.desktop.live_preview import CameraPreviewPanel, _PreviewReader, _PreviewTile, online_camera_sources, preview_camera_source
from visitor_counter.desktop.pages import OverviewPage


@pytest.fixture(scope="module", autouse=True)
def qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app


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


def test_reolink_preview_preserves_main_stream_and_credentials() -> None:
    source = "rtsp://fake:fixture@192.168.1.11:554/h264Preview_01_main?channel=1"
    assert preview_camera_source(source) == source
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
        timestamp=1_700_000_000,
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
        timestamp=1_700_000_000,
        cameras=[{"camera_id": "camera_1", "name": "Eingang", "status": "ONLINE", "obstructed": True}],
        runtime={"detector_active": True, "inference_fps": 8},
    ))
    assert "blockiert die Zählung für: Eingang" in page.inference_info.text()
    page.close()


def test_expanded_preview_preserves_native_image_pixels() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    panel = CameraPreviewPanel()
    panel._tiles["camera_1"] = _PreviewTile("camera_1", "Entrance", lambda: None)
    image = QImage(2560, 1920, QImage.Format_RGB888)
    image.fill(0)
    panel._last_images["camera_1"] = image
    panel._expand("camera_1")
    app.processEvents()
    assert panel._dialog_label.pixmap().size() == image.size()
    assert panel._dialog_label.size() == image.size()
    panel._dialog.close()
    panel.shutdown()


def test_reader_decodes_shared_frame_without_opening_camera(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assert app is not None
    panel = CameraPreviewPanel()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "camera_2.jpg"), frame)
    (tmp_path / "camera_2.json").write_text(json.dumps({"written_at": time()}))
    # This RTSP URL deliberately cannot be reached. The shared frame alone is
    # sufficient, and the reader must never attempt a camera connection.
    reader = _PreviewReader("camera_2", "rtsp://invalid.invalid/never-open", panel, tmp_path)
    reader.output_dir = tmp_path
    images = []
    def received(camera_id, image):
        images.append((camera_id, image))
        reader.stop()
    reader.image_ready.connect(received, Qt.DirectConnection)
    # Exercise the actual decode loop synchronously; the direct receiver stops
    # it at the first verified frame without a platform-dependent nested GUI loop.
    deadline = Timer(3.0, reader.stop)
    deadline.start()
    try:
        reader.run()
    finally:
        reader.stop()
        deadline.cancel()
    assert len(images) == 1
    assert images[0][0] == "camera_2"
    assert images[0][1].width() == 640
    assert images[0][1].height() == 480
    panel.close()
