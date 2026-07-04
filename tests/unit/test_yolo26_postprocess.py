from __future__ import annotations

import numpy as np

from visitor_counter.hailo_manager import parse_yolo26_coco_output


def _raw() -> np.ndarray:
    return np.zeros((84, 8400), dtype=np.float32)


def test_yolo26_rejects_invalid_tensor_shape() -> None:
    detections = parse_yolo26_coco_output(np.zeros((10, 10), dtype=np.float32), 1280, 720, 0.2)
    assert detections == []


def test_yolo26_returns_no_detection_without_person_score() -> None:
    raw = _raw()
    raw[5, 0] = 0.99
    detections = parse_yolo26_coco_output(raw, 1280, 720, 0.2)
    assert detections == []


def test_yolo26_decodes_person_box() -> None:
    raw = _raw()
    raw[:4, 0] = [320, 320, 100, 200]
    raw[4, 0] = 0.95
    detections = parse_yolo26_coco_output(raw, 1280, 720, 0.2)
    assert len(detections) == 1
    assert detections[0].class_id == 0
    assert detections[0].label == "person"
    assert abs(detections[0].confidence - 0.95) < 1e-6


def test_yolo26_nms_suppresses_overlapping_persons() -> None:
    raw = _raw()
    raw[:4, 0] = [320, 320, 100, 200]
    raw[4, 0] = 0.95
    raw[:4, 1] = [322, 322, 100, 200]
    raw[4, 1] = 0.90
    detections = parse_yolo26_coco_output(raw, 1280, 720, 0.2, iou_threshold=0.60)
    assert len(detections) == 1


def test_yolo26_respects_max_detections() -> None:
    raw = _raw()
    for index in range(20):
        raw[:4, index] = [20 + index * 30, 300, 20, 40]
        raw[4, index] = 0.99 - (index * 0.01)
    detections = parse_yolo26_coco_output(raw, 1280, 720, 0.2, max_detections=5)
    assert len(detections) == 5
