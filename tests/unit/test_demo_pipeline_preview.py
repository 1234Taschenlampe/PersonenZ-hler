"""Preview quality must not interfere with the two-camera AI pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PySide6.QtWidgets import QApplication

from visitor_counter.configuration import AppConfig
from visitor_counter.desktop.pages import PrivacyPage
from visitor_counter.inference_pipeline import ProcessingPipeline
from visitor_counter.types import FramePacket
from visitor_counter.video_stream import LocalPreviewExporter


def test_hd_line_overlay_matches_actual_inference_frame() -> None:
    pipeline = object.__new__(ProcessingPipeline)
    pipeline.config = AppConfig()
    pipeline.config.display.show_camera_preview = True
    pipeline.config.display.anonymization_mode = "none"
    pipeline.config.cameras["camera_1"].counting_mode = "line"
    pipeline.counters = {"camera_1": SimpleNamespace(
        _tracks={}, counts=SimpleNamespace(entered=0, exited=0)
    )}
    source = np.full((1080, 1920, 3), 140, dtype=np.uint8)
    packet = FramePacket.from_image("camera_1", 1, source, 1.0)
    annotated = pipeline._annotate(packet, [])
    assert annotated.shape == (1080, 1920, 3)
    # Configured line y=360 at 1280x720 -> actual y=540 at 1920x1080.
    assert annotated[540, 1000].tolist() == [0, 220, 255]
    assert source[540, 1000].tolist() == [140, 140, 140]


def test_preanonymized_local_preview_does_not_pixelate_boxes_again(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "visitor_counter.video_stream.local_preview_directory",
        lambda _root: tmp_path / "ram",
    )
    exporter = LocalPreviewExporter(tmp_path, enabled=False)
    exporter.enabled = True
    exporter.output_dir.mkdir()
    # The inference pipeline has already masked the scene; this crisp green
    # diagnostic line must survive the local export unpixelated.
    frame = np.full((1920, 2560, 3), 95, dtype=np.uint8)
    cv2.line(frame, (200, 960), (1400, 960), (0, 255, 0), 5)
    exporter._write_frame("camera_1", frame, ())
    image = cv2.imread(str(exporter.output_dir / "camera_1.jpg"))
    assert image.shape[:2] == (1080, 1440)
    assert image[540, 500, 1] > 190
    assert image[540, 500, 0] < 80
    meta = json.loads((exporter.output_dir / "camera_1.json").read_text())
    assert meta["anonymized"] is True
    exporter.close()


def test_local_preview_setting_is_raw_while_remote_setting_stays_anonymized() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    page = PrivacyPage()
    config = AppConfig()
    config.display.show_camera_preview = True
    page.set_config(config)
    assert config.display.anonymization_mode == "none"
    emitted = []
    page.save_requested.connect(emitted.append)
    page._emit_save()
    assert emitted[0]["display.anonymization_mode"] == "none"
    assert emitted[0]["display.show_camera_preview"] is True
    page.remote_video.setChecked(True)
    page._emit_save()
    assert emitted[-1]["display.anonymization_mode"] == "full_frame"
    page.close()
