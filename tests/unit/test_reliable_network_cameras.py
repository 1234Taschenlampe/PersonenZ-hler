"""Camera discovery and connection regression tests (no camera hardware needed)."""
from __future__ import annotations

import ipaddress
from threading import Event

import cv2
import pytest

from visitor_counter import network_camera_discovery as discovery
from visitor_counter import camera_manager
from visitor_counter.configuration import CameraConfig
from visitor_counter.camera_manager import CameraCapture, LatestFrameHub


def test_onvif_only_candidate_does_not_pretend_rtsp_is_ready(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "scan_rtsp_network", lambda cidr="": [
        discovery.RtspCandidate("192.168.15.10", 554),
    ])
    monkeypatch.setattr(discovery, "discover_onvif_hosts", lambda: [
        "192.168.15.10", "192.168.15.12", "192.168.16.33",
    ])
    results = discovery.discover_network_cameras("192.168.15.0/24")
    assert [result.host for result in results] == [
        "192.168.15.10", "192.168.15.12"
    ]
    assert results[0].rtsp_ready is True
    assert results[1].rtsp_ready is False
    assert "unbestätigt" in results[1].label


def test_discovery_rejects_public_networks_without_contacting_network(monkeypatch) -> None:
    monkeypatch.setattr(
        discovery, "scan_rtsp_network", lambda _cidr: pytest.fail("Never scan public LAN")
    )
    monkeypatch.setattr(
        discovery, "discover_onvif_hosts", lambda: pytest.fail("No multicast")
    )
    with pytest.raises(ValueError):
        discovery.discover_network_cameras("8.8.8.0/24")


def test_shared_camera_open_sets_tcp_timeouts_without_overriding_operator(monkeypatch) -> None:
    observed = []

    class Capture:
        def __init__(self, *args):
            observed.append(args)

    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    monkeypatch.setattr(cv2, "VideoCapture", Capture)
    camera_manager.open_camera_source("rtsp://192.168.1.11:554/Preview_01_sub")
    assert observed[0][1] == cv2.CAP_FFMPEG
    assert cv2.CAP_PROP_OPEN_TIMEOUT_MSEC in observed[0][2]
    assert cv2.CAP_PROP_READ_TIMEOUT_MSEC in observed[0][2]
    assert camera_manager.os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "rtsp_transport;tcp"
    monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;udp")
    camera_manager.open_camera_source("rtsp://192.168.1.12/Preview_01_sub")
    assert camera_manager.os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "rtsp_transport;udp"


def test_invalid_camera_input_does_not_mark_online() -> None:
    config = CameraConfig(camera_id="camera_1", device="rtsp://10.0.0.12/test")
    camera = CameraCapture(config, LatestFrameHub(["camera_1"]), Event())
    camera._mark_failure("RTSP negotiation failed")
    assert not camera.stats.connected
    assert camera.stats.fps == 0
    assert camera.stats.state == "RECONNECTING"


def test_private_camera_network_predicate() -> None:
    assert discovery._is_lan(ipaddress.IPv4Address("192.168.55.9"))
    assert not discovery._is_lan(ipaddress.IPv4Address("8.8.8.8"))
