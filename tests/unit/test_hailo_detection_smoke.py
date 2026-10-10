from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from scripts import verify_hailo_detection as smoke
from visitor_counter.configuration import AppConfig
from visitor_counter.types import BoundingBox, Detection


def test_smoke_reports_actual_tensor_metadata_and_releases_detector(monkeypatch, tmp_path):
    class FakeDetector:
        closed = False

        def __init__(self, *args):
            self._infer_model = SimpleNamespace(input=lambda: SimpleNamespace(shape=(640, 640, 3)))
            self._onnx_session = object()
            self.hef_sha256 = "digest"
            self.hailo_architecture = "HAILO10H"
            self.output_shapes = {"classes": [80, 80, 80]}
            self.last_latency_ms = 4.5
            self.last_stage_ms = {"decode_model_output_ms": 2.0}
            self.inference_count = 0

        def initialize(self):
            pass

        def _preprocess(self, image):
            return np.zeros((1, 640, 640, 3), dtype=np.uint8), {}

        def infer(self, image):
            self.inference_count += 1
            return [Detection(BoundingBox(10, 20, 60, 100), .9)]

        def close(self):
            FakeDetector.closed = True

    monkeypatch.setattr(smoke, "ObservedHailoManager", FakeDetector)
    report = smoke.verify_image(AppConfig(), tmp_path, np.zeros((1920, 2560, 3), dtype=np.uint8), runs=2)
    assert (report["native_width"], report["native_height"]) == (2560, 1920)
    assert report["input_shape"] == [1, 640, 640, 3]
    assert report["output_shapes"] == {"classes": [80, 80, 80]}
    assert report["person_detected_each_run"]
    assert report["inference_count"] == 2
    assert report["runs"][0]["persons"][0]["box_xyxy"] == [10, 20, 60, 100]
    assert FakeDetector.closed


def test_smoke_initialization_failure_releases_hailo_resources(monkeypatch, tmp_path):
    class FailingDetector:
        closed = False

        def __init__(self, *args):
            pass

        def initialize(self):
            raise RuntimeError("device busy")

        def close(self):
            FailingDetector.closed = True

    monkeypatch.setattr(smoke, "ObservedHailoManager", FailingDetector)
    with pytest.raises(RuntimeError, match="device busy"):
        smoke.verify_image(AppConfig(), tmp_path, np.zeros((64, 64, 3), dtype=np.uint8))
    assert FailingDetector.closed


def test_smoke_error_report_omits_private_filename_and_config(capsys, monkeypatch):
    monkeypatch.setattr(smoke.logging, "disable", lambda level: None)
    result = smoke.main(["--config", "password-secret.yaml", "--image", "does-not-exist-private-photo.jpg"])
    output = capsys.readouterr().out
    assert result == 1
    assert "FileNotFoundError" in output
    assert "password-secret" not in output
    assert "private-photo" not in output
