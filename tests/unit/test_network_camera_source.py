from __future__ import annotations

from visitor_counter.camera_manager import camera_source_kind, is_network_camera_source


def test_rtsp_source_is_network_camera() -> None:
    source = "rtsp://192.168.50.21:554/stream"
    assert is_network_camera_source(source)
    assert camera_source_kind(source) == "RTSP"


def test_http_source_is_network_camera() -> None:
    assert is_network_camera_source("http://192.168.50.22/video")
    assert camera_source_kind("http://192.168.50.22/video") == "HTTP"


def test_v4l2_source_remains_usb() -> None:
    assert not is_network_camera_source("/dev/video0")
    assert camera_source_kind("/dev/video0") == "USB"
