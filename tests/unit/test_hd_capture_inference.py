"""HD capture and Hailo RGB preprocessing regression tests."""
from __future__ import annotations

from threading import Event

import numpy as np

from visitor_counter.camera_manager import CameraCapture, LatestFrameHub
from visitor_counter.configuration import CameraConfig, ModelConfig
from visitor_counter.hailo_manager import HailoManager


def test_hailo_preprocess_converts_opencv_bgr_to_rgb(tmp_path) -> None:
    manager = HailoManager(ModelConfig(input_size=640), tmp_path / "unused.hef")
    # Bright red in OpenCV BGR must remain bright red in HEF RGB.
    source = np.zeros((1080, 1920, 3), dtype=np.uint8)
    source[:, :, 2] = 255
    tensor, metrics = manager._preprocess(source)
    assert source.shape == (1080, 1920, 3)
    assert tensor.shape == (1, 640, 640, 3)
    assert tensor.dtype == np.uint8
    assert tensor[0, 320, 320].tolist() == [255, 0, 0]
    assert tensor[0, 0, 0].tolist() == [114, 114, 114]
    assert metrics["color_convert_ms"] >= 0


def test_capture_exposes_actual_decoded_hd_resolution() -> None:
    camera = CameraConfig(camera_id="camera_1", width=1280, height=720)
    hub = LatestFrameHub(["camera_1"])
    capture = CameraCapture(camera, hub, Event())
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    class FakeCapture:
        reads = 0

        def read(self):
            self.reads += 1
            return (True, frame) if self.reads == 1 else (False, None)

    capture._capture_loop(FakeCapture())
    assert (capture.stats.frame_width, capture.stats.frame_height) == (1920, 1080)
    packet = hub.get_next(["camera_1"], timeout=0)
    assert packet is not None
    assert (packet.width, packet.height) == (1920, 1080)
