"""Shared preview stays native and leaves remote-video privacy unchanged."""
from __future__ import annotations

import json
from pathlib import Path
from time import monotonic

import cv2
import numpy as np
import pytest

from visitor_counter.video_stream import FrameStreamExporter, LocalPreviewExporter


@pytest.fixture(autouse=True)
def isolated_preview_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Hardware test runs must never clear a production /dev/shm preview.
    monkeypatch.setattr("visitor_counter.video_stream.local_preview_directory", lambda root: tmp_path / "local")
    monkeypatch.setattr("visitor_counter.video_stream.stream_frame_directory", lambda root: tmp_path / "remote")


def test_local_preview_exports_native_decoded_size(tmp_path: Path) -> None:
    exporter = LocalPreviewExporter(tmp_path, enabled=False)
    exporter.output_dir = tmp_path / "preview"
    exporter.output_dir.mkdir()
    frame = np.zeros((1920, 2560, 3), dtype=np.uint8)
    exporter._write_frame("camera_1", frame, ())
    decoded = cv2.imread(str(exporter.output_dir / "camera_1.jpg"))
    assert decoded.shape[:2] == (1920, 2560)
    metadata = json.loads((exporter.output_dir / "camera_1.json").read_text())
    assert metadata["native_width"] == metadata["width"] == 2560
    assert metadata["native_height"] == metadata["height"] == 1920
    assert metadata["anonymized"] is True
    exporter.close()
    assert not exporter.output_dir.exists()


def test_remote_video_still_rejects_raw_frames(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="without anonymization"):
        FrameStreamExporter(tmp_path, enabled=True, anonymization_mode="none")


def test_preview_queue_keeps_only_latest_frame_per_camera(tmp_path: Path) -> None:
    exporter = LocalPreviewExporter(tmp_path, enabled=False)
    exporter.enabled = True  # inspect bounded submission without a consumer thread
    exporter._min_interval = 0
    for value in range(10):
        exporter.submit("camera_1", np.full((8, 8, 3), value, dtype=np.uint8))
    exporter.submit("camera_2", np.zeros((8, 8, 3), dtype=np.uint8))
    assert len(exporter._pending) == 2
    assert exporter._pending["camera_1"][0][0, 0, 0] == 9
    exporter.close()


def test_rate_limit_drops_intermediate_frames(tmp_path: Path) -> None:
    exporter = LocalPreviewExporter(tmp_path, enabled=False, target_fps=5)
    exporter.enabled = True
    exporter._last_submit_at["camera_1"] = monotonic()
    exporter.submit("camera_1", np.zeros((8, 8, 3), dtype=np.uint8))
    assert not exporter._pending
    exporter.close()
