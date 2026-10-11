"""Acceptance regressions for direction mapping and stream resilience."""
from __future__ import annotations

from threading import Event
from time import time
from types import SimpleNamespace

import cv2
import numpy as np

from visitor_counter.camera_manager import CameraCapture, LatestFrameHub
from visitor_counter.configuration import AppConfig, CameraConfig, TrackingConfig
from visitor_counter.counter import LineCrossingCounter
from visitor_counter.inference_pipeline import ProcessingPipeline
from visitor_counter.types import BoundingBox, CountingLine, FramePacket, TrackState, TrackedObject


def _track(y: float, frame_id: int) -> TrackedObject:
    return TrackedObject(
        track_id=4,
        bbox=BoundingBox(80, max(0, y - 22), 120, min(200, y + 25)),
        confidence=0.92,
        camera_id="camera_1",
        global_person_id=4,
        state=TrackState.CONFIRMED,
        hits=frame_id,
    )


def test_approach_to_image_edge_without_crossing_never_counts() -> None:
    camera = CameraConfig(
        camera_id="camera_1", width=200, height=200,
        counting_mode="exit_edge", disappearance_frames=3,
        edge_margin_pixels=40,
    )
    counter = LineCrossingCounter(
        "camera_1", CountingLine((0, 100), (200, 100)),
        TrackingConfig(
            min_confirmed_track_hits=3,
            minimum_bbox_area=50,
            minimum_confidence=0.3,
        ), camera,
    )
    # The entire track stays in zone B, yet moves far enough toward the
    # bottom edge that motion-only inference used to count a false entry.
    for frame, y in enumerate((120, 130, 145, 165, 180, 195), start=1):
        assert counter.update(frame, [_track(y, frame)], (200, 200)) == []
    for frame in range(7, 14):
        assert counter.update(frame, [], (200, 200)) == []
    assert counter.counts.entered == counter.counts.exited == 0


def test_vertical_reference_line_draws_correct_left_right_directions() -> None:
    pipeline = object.__new__(ProcessingPipeline)
    config = AppConfig()
    config.display.show_camera_preview = True
    config.display.anonymization_mode = "none"
    cam = config.cameras["camera_1"]
    cam.width = cam.height = 200
    cam.counting_mode = "exit_edge"
    cam.edge_margin_pixels = 30
    cam.entry_direction, cam.exit_direction = "A_to_B", "B_to_A"
    pipeline.config = config
    pipeline.counters = {
        "camera_1": SimpleNamespace(
            normal_vector=(1.0, 0.0),
            counts=SimpleNamespace(entered=0, exited=0),
        ),
    }
    image = np.full((200, 200, 3), 80, dtype=np.uint8)
    frame = FramePacket.from_image("camera_1", 1, image, time())
    rendered = pipeline._annotate(frame, [])
    # For a positive X normal, left border is A (OUT); right is B (IN).
    assert rendered[150, 30].tolist() == [0, 160, 255]
    assert rendered[150, 169].tolist() == [0, 230, 100]


def test_opencv_read_exception_reconnects_instead_of_killing_capture_worker() -> None:
    class BrokenStream:
        def read(self):
            raise cv2.error("simulated transient RTSP decode exception")

    capture = CameraCapture(
        CameraConfig(camera_id="camera_1", device="rtsp://127.0.0.1:554/test"),
        LatestFrameHub(["camera_1"]),
        Event(),
    )
    capture._capture_loop(BrokenStream())
    assert capture.stats.decode_errors == 1
    assert capture.stats.reconnect_count == 1
    assert capture.stats.state == "RECONNECTING"
    assert capture.stats.connected is False
