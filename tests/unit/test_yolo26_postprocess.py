from __future__ import annotations

import numpy as np
import pytest

from visitor_counter.hailo_manager import (
    HailoUnavailableError,
    map_hef_outputs_to_onnx_inputs,
    parse_yolo26_coco_output,
    parse_yolo26_postprocess_output,
)


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


def test_yolo26_postprocess_filters_person_class() -> None:
    raw = np.zeros((1, 300, 6), dtype=np.float32)
    raw[0, 0] = [160, 180, 320, 460, 0.91, 0]
    raw[0, 1] = [10, 10, 200, 200, 0.99, 2]
    detections = parse_yolo26_postprocess_output(raw, 1280, 720, 0.2)
    assert len(detections) == 1
    assert detections[0].class_id == 0
    assert detections[0].label == "person"


def test_hailo_equal_shape_classification_head_keeps_person_channel() -> None:
    # Native HEF conv74 is HWC=(80,80,80). Equal dimensions must never be
    # mistaken for CHW: spatial pixel (12,34), person channel 0 stays there.
    native = np.zeros((80, 80, 80), dtype=np.float32)
    native[12, 34, 0] = 0.91
    mapped = map_hef_outputs_to_onnx_inputs(
        {"yolo26m/conv74": native},
        {"yolo26m/conv74": ["classes", [80, 80, 80]]},
    )["classes"]
    assert mapped.shape == (1, 80, 80, 80)
    assert mapped[0, 0, 12, 34] == pytest.approx(0.91)
    assert mapped[0, 12, 34, 0] == 0
    assert mapped.flags.c_contiguous


def test_hailo_non_square_channels_map_with_existing_batch() -> None:
    native = np.zeros((1, 40, 40, 4), dtype=np.float32)
    native[0, 7, 9, 2] = 16
    mapped = map_hef_outputs_to_onnx_inputs(
        {"boxes": native}, {"boxes": ["onnx_boxes", [4, 40, 40]]}
    )["onnx_boxes"]
    assert mapped.shape == (1, 4, 40, 40)
    assert mapped[0, 2, 7, 9] == 16


def test_reference_onnx_mapping_can_explicitly_preserve_nchw() -> None:
    native = np.zeros((1, 80, 80, 80), dtype=np.float32)
    native[0, 0, 12, 34] = 0.91
    mapped = map_hef_outputs_to_onnx_inputs(
        {"classes": native}, {"classes": ["onnx_classes", [80, 80, 80]]}, source_layout="NCHW"
    )["onnx_classes"]
    np.testing.assert_array_equal(mapped, native)


def test_hailo_mapping_rejects_shape_mismatch_and_quantized_scores() -> None:
    mapping = {"classes": ["onnx_classes", [80, 40, 40]]}
    with pytest.raises(HailoUnavailableError, match="Shape mismatch"):
        map_hef_outputs_to_onnx_inputs({"classes": np.zeros((20, 20, 80))}, mapping)
    with pytest.raises(HailoUnavailableError, match="dequantization"):
        map_hef_outputs_to_onnx_inputs({"classes": np.zeros((40, 40, 80), dtype=np.uint8)}, mapping)
