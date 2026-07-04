from __future__ import annotations

from threading import Event
from time import monotonic, time

import numpy as np

from visitor_counter.camera_manager import CameraCapture, LatestFrameHub
from visitor_counter.configuration import CameraConfig
from visitor_counter.types import FramePacket, LatencyWindow


def _packet(camera_id: str, frame_id: int) -> FramePacket:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    return FramePacket.from_image(camera_id, frame_id, image, time())


def test_latest_frame_hub_replaces_old_frame_per_camera() -> None:
    hub = LatestFrameHub(["camera_1", "camera_2"])

    assert hub.put(_packet("camera_1", 1)) is False
    assert hub.put(_packet("camera_1", 2)) is True

    packet = hub.get_next(["camera_1", "camera_2"], timeout=0.0)
    assert packet is not None
    assert packet.camera_id == "camera_1"
    assert packet.frame_id == 2
    assert hub.dropped_counts()["camera_1"] == 1
    assert hub.qsize() == 0


def test_latest_frame_hub_alternates_after_last_camera() -> None:
    hub = LatestFrameHub(["camera_1", "camera_2"])
    hub.put(_packet("camera_1", 1))
    hub.put(_packet("camera_2", 1))

    packet = hub.get_next(["camera_1", "camera_2"], last_camera_id="camera_1", timeout=0.0)

    assert packet is not None
    assert packet.camera_id == "camera_2"


def test_latest_frame_hub_drops_stale_frame() -> None:
    hub = LatestFrameHub(["camera_1"])
    packet = _packet("camera_1", 1)
    stale = FramePacket(
        camera_id=packet.camera_id,
        frame_id=packet.frame_id,
        monotonic_time=monotonic() - 10.0,
        captured_at=packet.captured_at,
        width=packet.width,
        height=packet.height,
        image=packet.image,
    )
    hub.put(stale)

    assert hub.get_next(["camera_1"], timeout=0.0, max_age_seconds=0.5) is None
    assert hub.dropped_counts()["camera_1"] == 1


def test_camera_capture_publishes_to_hub_and_callback() -> None:
    class FakeCapture:
        def __init__(self) -> None:
            self.reads = 0

        def read(self) -> tuple[bool, np.ndarray | None]:
            self.reads += 1
            return True, np.zeros((8, 12, 3), dtype=np.uint8)

    hub = LatestFrameHub(["camera_1"])
    stop_event = Event()
    callback_packets: list[FramePacket] = []

    def on_frame(packet: FramePacket) -> None:
        callback_packets.append(packet)
        stop_event.set()

    capture = CameraCapture(CameraConfig(camera_id="camera_1"), hub, stop_event, frame_callback=on_frame)
    capture._capture_loop(FakeCapture())  # noqa: SLF001 - focused unit test for capture fan-out

    queued = hub.get_next(["camera_1"], timeout=0.0)
    assert queued is not None
    assert callback_packets
    assert queued.frame_id == callback_packets[0].frame_id == 1
    assert queued.image.shape == callback_packets[0].image.shape == (8, 12, 3)


def test_latency_window_reports_summary_statistics() -> None:
    window = LatencyWindow(max_samples=5)
    for value in [1.0, 2.0, 3.0]:
        window.add({"end_to_end_ms": value})

    summary = window.summaries()["end_to_end_ms"]

    assert summary.count == 3
    assert summary.mean_ms == 2.0
    assert summary.median_ms == 2.0
    assert summary.p95_ms == 2.0
    assert summary.max_ms == 3.0
