from __future__ import annotations

import json
import logging
import subprocess
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from .configuration import ModelConfig
from .types import BoundingBox, Detection

LOGGER = logging.getLogger(__name__)


class HailoUnavailableError(RuntimeError):
    pass


class HailoManager:
    def __init__(self, config: ModelConfig, hef_path: Path) -> None:
        self.config = config
        self.hef_path = hef_path
        self.ready = False
        self.status = "not initialized"
        self.last_latency_ms = 0.0
        self.last_stage_ms: dict[str, float] = {}
        self.inference_count = 0
        self.backend = "HailoRT"
        self.hailo_device = ""
        self.hailo_architecture = ""
        self.hef_sha256 = ""
        self._hailo_module: object | None = None
        self._hef: object | None = None
        self._vdevice: object | None = None
        self._infer_model: object | None = None
        self._configured_model: object | None = None
        self._config_ctx: object | None = None
        self._input_name: str | None = None
        self._onnx_config: dict | None = None
        self._onnx_session: object | None = None

    def initialize(self) -> None:
        if not self.hef_path.exists():
            self.status = f"HEF not found: {self.hef_path}"
            LOGGER.error(self.status)
            raise HailoUnavailableError(self.status)
        try:
            import hailo_platform  # type: ignore[import-not-found]

            self._hailo_module = hailo_platform
        except ImportError as exc:
            self.status = "hailo_platform Python package not available"
            LOGGER.error(self.status)
            raise HailoUnavailableError(self.status) from exc

        try:
            self.hef_sha256 = _sha256_file(self.hef_path)
            self.hailo_architecture = detect_hailo_architecture()
            self.hailo_device = detect_hailo_device()
            params = hailo_platform.VDevice.create_params()
            if hasattr(params, "scheduling_algorithm"):
                params.scheduling_algorithm = hailo_platform.HailoSchedulingAlgorithm.ROUND_ROBIN
            if hasattr(params, "group_id"):
                params.group_id = "SHARED"
            self._vdevice = hailo_platform.VDevice(params)
            self._hef = hailo_platform.HEF(str(self.hef_path))
            self._infer_model = self._vdevice.create_infer_model(str(self.hef_path))
            self._infer_model.set_batch_size(1)
            self._infer_model.input().set_format_type(hailo_platform.FormatType.UINT8)
            for output_name in self._infer_model.output_names:
                self._infer_model.output(output_name).set_format_type(hailo_platform.FormatType.FLOAT32)
            self._config_ctx = self._infer_model.configure()
            self._configured_model = self._config_ctx.__enter__()
            input_infos = self._hef.get_input_vstream_infos()
            if not input_infos:
                raise HailoUnavailableError("HEF has no input vstream")
            self._input_name = self._infer_model.input_names[0]
            self._initialize_postprocess()
        except Exception as exc:  # noqa: BLE001
            self.status = f"Failed to configure HEF on Hailo: {exc}"
            LOGGER.error(self.status)
            self.close()
            raise HailoUnavailableError(self.status) from exc

        self.ready = True
        self.status = f"{self.config.model_name} - Hailo-Inferenz aktiv ({self.hef_path.name}, {self.hef_sha256[:12]}, {self.hailo_architecture})"
        LOGGER.info(self.status)

    def infer(self, image: np.ndarray) -> list[Detection]:
        if (
            not self.ready
            or self._hailo_module is None
            or self._infer_model is None
            or self._configured_model is None
            or self._input_name is None
        ):
            raise HailoUnavailableError("HailoManager is not ready")
        total_start = perf_counter()
        tensor, preprocess_ms = self._preprocess(image)
        try:
            bind_start = perf_counter()
            output_buffers = {
                name: np.empty(self._infer_model.output(name).shape, dtype=np.float32)
                for name in self._infer_model.output_names
            }
            bindings = self._configured_model.create_bindings(output_buffers=output_buffers)
            bindings.input(self._input_name).set_buffer(tensor)
            bind_end = perf_counter()
            infer_start = perf_counter()
            self._configured_model.run([bindings], 10000)
            infer_end = perf_counter()
            output_start = perf_counter()
            outputs = {name: bindings.output(name).get_buffer() for name in self._infer_model.output_names}
            output_end = perf_counter()
        except Exception as exc:  # noqa: BLE001
            self.status = f"Hailo inference failed: {exc}"
            LOGGER.error(self.status)
            raise HailoUnavailableError(self.status) from exc
        decode_start = perf_counter()
        detections = self._decode_outputs(outputs, image.shape[1], image.shape[0])
        decode_end = perf_counter()
        self.last_latency_ms = (infer_end - infer_start) * 1000.0
        self.inference_count += 1
        self.last_stage_ms = {
            **preprocess_ms,
            "hailo_wait_ms": max(0.0, (bind_start - total_start) * 1000.0 - sum(preprocess_ms.values())),
            "hailo_input_transfer_ms": (bind_end - bind_start) * 1000.0,
            "hailo_inference_ms": self.last_latency_ms,
            "hailo_output_transfer_ms": (output_end - output_start) * 1000.0,
            "decode_model_output_ms": (decode_end - decode_start) * 1000.0,
            "nms_ms": 0.0 if any(isinstance(value, list) for value in outputs.values()) else self.last_stage_ms.get("nms_ms", 0.0),
            "hailo_total_call_ms": (decode_end - total_start) * 1000.0,
        }
        return detections

    def close(self) -> None:
        if self._config_ctx is not None:
            try:
                self._config_ctx.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Hailo configured model release failed: %s", exc)
        self._config_ctx = None
        self._configured_model = None
        self._infer_model = None
        if self._vdevice is not None and hasattr(self._vdevice, "release"):
            try:
                self._vdevice.release()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Hailo VDevice release failed: %s", exc)
        self._vdevice = None
        self.ready = False

    def _preprocess(self, image: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
        model_w = self.config.input_size
        model_h = self.config.input_size
        img_h, img_w = image.shape[:2]
        scale = min(model_w / img_w, model_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        resize_start = perf_counter()
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        resize_end = perf_counter()
        letterbox_start = perf_counter()
        padded = np.full((model_h, model_w, 3), (114, 114, 114), dtype=np.uint8)
        x_offset = (model_w - new_w) // 2
        y_offset = (model_h - new_h) // 2
        padded[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized
        tensor = np.ascontiguousarray(padded[np.newaxis, ...])
        letterbox_end = perf_counter()
        return tensor, {
            "jpeg_decode_ms": 0.0,
            "color_convert_ms": 0.0,
            "resize_ms": (resize_end - resize_start) * 1000.0,
            "letterbox_ms": (letterbox_end - letterbox_start) * 1000.0,
        }

    def _decode_outputs(self, outputs: dict[str, np.ndarray], original_width: int, original_height: int) -> list[Detection]:
        if not outputs:
            return []
        if self.config.output_format == "yolo26_pose":
            return self._decode_yolo26_pose_outputs(outputs, original_width, original_height)
        if self.config.output_format == "yolo26_detection" and self._onnx_session is not None:
            return self._decode_yolo26_detection_outputs(outputs, original_width, original_height)
        for value in outputs.values():
            if isinstance(value, list):
                return self._decode_hailo_nms_list(value, original_width, original_height)
        arrays = [np.asarray(value) for value in outputs.values() if not isinstance(value, list)]
        flat_candidates: list[np.ndarray] = []
        for array in arrays:
            squeezed = np.squeeze(array)
            if squeezed.ndim == 2 and 84 in squeezed.shape:
                return parse_yolo26_coco_output(
                    squeezed,
                    original_width,
                    original_height,
                    self.config.confidence_threshold,
                    self.config.input_size,
                    self.config.iou_threshold,
                    self.config.max_detections,
                )
            if squeezed.ndim == 2 and squeezed.shape[-1] >= 6:
                flat_candidates.append(squeezed)
            elif squeezed.ndim == 3 and squeezed.shape[-1] >= 6:
                flat_candidates.append(squeezed.reshape(-1, squeezed.shape[-1]))
        if not flat_candidates:
            LOGGER.warning("Unsupported Hailo output shapes: %s", [list(array.shape) for array in arrays])
            return []
        raw = max(flat_candidates, key=lambda item: item.shape[0])
        nms_start = perf_counter()
        detections = parse_yolo_like_output(
            raw,
            original_width,
            original_height,
            self.config.confidence_threshold,
            self.config.input_size,
            self.config.iou_threshold,
            self.config.max_detections,
        )
        self.last_stage_ms["nms_ms"] = (perf_counter() - nms_start) * 1000.0
        return detections

    def _decode_hailo_nms_list(self, classes: list, original_width: int, original_height: int) -> list[Detection]:
        rows = np.asarray(classes[0], dtype=np.float32) if classes else np.empty((0, 5), dtype=np.float32)
        if rows.ndim != 2 or rows.shape[1] < 5:
            return []
        parsed: list[Detection] = []
        model_size = float(self.config.input_size)
        for row in rows:
            y1, x1, y2, x2, confidence = [float(value) for value in row[:5]]
            if confidence < self.config.confidence_threshold:
                continue
            coords = np.asarray([x1 * model_size, y1 * model_size, x2 * model_size, y2 * model_size], dtype=np.float32)
            bbox = self._map_model_box_to_original(coords, original_width, original_height)
            if bbox.width <= 1 or bbox.height <= 1:
                continue
            parsed.append(Detection(bbox, confidence, class_id=0, label="person"))
        parsed.sort(key=lambda detection: detection.confidence, reverse=True)
        return parsed

    def _initialize_postprocess(self) -> None:
        if not self.config.postprocess_config_path and not self.config.postprocess_onnx_path:
            return
        config_path = self._resolve_project_path(self.config.postprocess_config_path)
        onnx_path = self._resolve_project_path(self.config.postprocess_onnx_path)
        if not config_path.exists():
            raise HailoUnavailableError(f"ONNX postprocess config not found: {config_path}")
        if not onnx_path.exists():
            raise HailoUnavailableError(f"ONNX postprocess model not found: {onnx_path}")
        self._onnx_config = json.loads(config_path.read_text(encoding="utf-8"))
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]
        except ImportError as exc:
            raise HailoUnavailableError("onnxruntime Python package not available") from exc
        options = ort.SessionOptions()
        options.log_severity_level = 3
        self._onnx_session = ort.InferenceSession(str(onnx_path), sess_options=options, providers=["CPUExecutionProvider"])
        LOGGER.info("Loaded %s ONNX postprocess: %s", self.config.output_format, onnx_path)

    def _resolve_project_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        try:
            return self.hef_path.parents[1] / path
        except IndexError:
            return Path.cwd() / path

    def _decode_yolo26_pose_outputs(
        self,
        outputs: dict[str, np.ndarray],
        original_width: int,
        original_height: int,
    ) -> list[Detection]:
        if self._onnx_config is None or self._onnx_session is None:
            raise HailoUnavailableError("YOLO26 pose postprocess is not initialized")
        tensor_mapping = self._onnx_config.get("output_tensor_mapping", {})
        onnx_inputs = map_hef_outputs_to_onnx_inputs(outputs, tensor_mapping)
        output_names = [output.name for output in self._onnx_session.get_outputs()]
        onnx_results = self._onnx_session.run(output_names, onnx_inputs)
        detections = np.asarray(onnx_results[0])
        if detections.ndim == 3:
            detections = detections[0]
        if detections.ndim != 2 or detections.shape[1] < 6:
            LOGGER.warning("Unsupported YOLO26 pose postprocess shape: %s", detections.shape)
            return []
        scores = detections[:, 4]
        valid = scores >= self.config.confidence_threshold
        rows = detections[valid]
        if rows.size == 0:
            return []
        rows = rows[np.argsort(-rows[:, 4])]
        parsed: list[Detection] = []
        for row in rows:
            class_id = int(row[5])
            if class_id != 0:
                continue
            bbox = self._map_model_box_to_original(row[:4], original_width, original_height)
            if bbox.width <= 1 or bbox.height <= 1:
                continue
            parsed.append(Detection(bbox, float(row[4]), class_id=0, label="person"))
        return parsed

    def _decode_yolo26_detection_outputs(
        self,
        outputs: dict[str, np.ndarray],
        original_width: int,
        original_height: int,
    ) -> list[Detection]:
        if self._onnx_config is None or self._onnx_session is None:
            raise HailoUnavailableError("YOLO26 detection postprocess is not initialized")
        tensor_mapping = self._onnx_config.get("output_tensor_mapping", {})
        onnx_inputs = map_hef_outputs_to_onnx_inputs(outputs, tensor_mapping)
        output_names = [output.name for output in self._onnx_session.get_outputs()]
        onnx_results = self._onnx_session.run(output_names, onnx_inputs)
        return parse_yolo26_postprocess_output(
            np.asarray(onnx_results[0], dtype=np.float32),
            original_width,
            original_height,
            self.config.confidence_threshold,
            self.config.input_size,
            self.config.max_detections,
        )

    def _map_model_box_to_original(self, coords: np.ndarray, original_width: int, original_height: int) -> BoundingBox:
        model_size = float(self.config.input_size)
        scale = min(model_size / original_width, model_size / original_height)
        new_w = int(original_width * scale)
        new_h = int(original_height * scale)
        x_offset = (model_size - new_w) / 2.0
        y_offset = (model_size - new_h) / 2.0
        x1, y1, x2, y2 = [float(value) for value in coords]
        x1 = (x1 - x_offset) / scale
        x2 = (x2 - x_offset) / scale
        y1 = (y1 - y_offset) / scale
        y2 = (y2 - y_offset) / scale
        x1 = max(0.0, min(x1, float(original_width)))
        x2 = max(0.0, min(x2, float(original_width)))
        y1 = max(0.0, min(y1, float(original_height)))
        y2 = max(0.0, min(y2, float(original_height)))
        return BoundingBox(x1, y1, x2, y2)


def parse_yolo_like_output(
    raw: np.ndarray,
    original_width: int,
    original_height: int,
    confidence_threshold: float,
    input_size: int = 640,
    iou_threshold: float = 0.50,
    max_detections: int = 300,
) -> list[Detection]:
    detections: list[Detection] = []
    if raw.ndim != 2 or raw.shape[1] < 6:
        return detections
    model_size = float(input_size)
    scale = min(model_size / original_width, model_size / original_height)
    new_w = int(original_width * scale)
    new_h = int(original_height * scale)
    x_offset = (model_size - new_w) / 2.0
    y_offset = (model_size - new_h) / 2.0
    rows = np.asarray(raw, dtype=np.float32)
    mask = (rows[:, 4] >= confidence_threshold) & (rows[:, 5].astype(np.int32) == 0)
    rows = rows[mask]
    if rows.size == 0:
        return detections
    if len(rows) > max_detections:
        rows = rows[np.argsort(-rows[:, 4])[:max_detections]]
    boxes = rows[:, :4].copy()
    if np.max(boxes) <= 1.5:
        boxes *= model_size
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - x_offset) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - y_offset) / scale
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0.0, float(original_width))
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0.0, float(original_height))
    valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    boxes = boxes[valid]
    scores = rows[:, 4][valid]
    keep = _nms_indices(boxes, scores, iou_threshold)
    for index in keep:
        x1, y1, x2, y2 = [float(value) for value in boxes[index]]
        detections.append(Detection(BoundingBox(x1, y1, x2, y2), float(scores[index]), class_id=0, label="person"))
    return detections


def parse_yolo26_coco_output(
    raw: np.ndarray,
    original_width: int,
    original_height: int,
    confidence_threshold: float,
    input_size: int = 640,
    iou_threshold: float = 0.60,
    max_detections: int = 300,
) -> list[Detection]:
    tensor = np.asarray(raw, dtype=np.float32)
    if tensor.ndim != 2:
        return []
    if tensor.shape[0] == 84:
        tensor = tensor.T
    if tensor.shape[1] != 84:
        return []
    scores = tensor[:, 4]
    candidate_mask = scores >= confidence_threshold
    if not np.any(candidate_mask):
        return []
    rows = tensor[candidate_mask]
    scores = rows[:, 4]
    if len(rows) > max_detections * 4:
        keep_top = np.argsort(-scores)[: max_detections * 4]
        rows = rows[keep_top]
        scores = scores[keep_top]
    boxes_xywh = rows[:, :4].copy()
    xyxy = np.empty_like(boxes_xywh)
    xyxy[:, 0] = boxes_xywh[:, 0] - (boxes_xywh[:, 2] / 2.0)
    xyxy[:, 1] = boxes_xywh[:, 1] - (boxes_xywh[:, 3] / 2.0)
    xyxy[:, 2] = boxes_xywh[:, 0] + (boxes_xywh[:, 2] / 2.0)
    xyxy[:, 3] = boxes_xywh[:, 1] + (boxes_xywh[:, 3] / 2.0)
    if np.max(xyxy) <= 1.5:
        xyxy *= float(input_size)
    boxes = _map_model_boxes_to_original(xyxy, original_width, original_height, input_size)
    valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
    boxes = boxes[valid]
    scores = scores[valid]
    keep = _nms_indices(boxes, scores, iou_threshold)[:max_detections]
    detections: list[Detection] = []
    for index in keep:
        x1, y1, x2, y2 = [float(value) for value in boxes[index]]
        detections.append(Detection(BoundingBox(x1, y1, x2, y2), float(scores[index]), class_id=0, label="person"))
    return detections


def parse_yolo26_postprocess_output(
    raw: np.ndarray,
    original_width: int,
    original_height: int,
    confidence_threshold: float,
    input_size: int = 640,
    max_detections: int = 300,
) -> list[Detection]:
    detections = np.asarray(raw, dtype=np.float32)
    if detections.ndim == 3:
        detections = detections[0]
    if detections.ndim != 2 or detections.shape[1] < 6:
        return []
    scores = detections[:, 4]
    class_ids = detections[:, 5].astype(np.int32)
    valid = (scores >= confidence_threshold) & (class_ids == 0)
    rows = detections[valid]
    if rows.size == 0:
        return []
    rows = rows[np.argsort(-rows[:, 4])[:max_detections]]
    boxes = _map_model_boxes_to_original(rows[:, :4], original_width, original_height, input_size)
    parsed: list[Detection] = []
    for row, box in zip(rows, boxes):
        x1, y1, x2, y2 = [float(value) for value in box]
        bbox = BoundingBox(x1, y1, x2, y2)
        if bbox.width <= 1 or bbox.height <= 1:
            continue
        parsed.append(Detection(bbox, float(row[4]), class_id=0, label="person"))
    return parsed


def _map_model_boxes_to_original(boxes: np.ndarray, original_width: int, original_height: int, input_size: int) -> np.ndarray:
    model_size = float(input_size)
    scale = min(model_size / original_width, model_size / original_height)
    new_w = int(original_width * scale)
    new_h = int(original_height * scale)
    x_offset = (model_size - new_w) / 2.0
    y_offset = (model_size - new_h) / 2.0
    mapped = boxes.copy()
    mapped[:, [0, 2]] = (mapped[:, [0, 2]] - x_offset) / scale
    mapped[:, [1, 3]] = (mapped[:, [1, 3]] - y_offset) / scale
    mapped[:, [0, 2]] = np.clip(mapped[:, [0, 2]], 0.0, float(original_width))
    mapped[:, [1, 3]] = np.clip(mapped[:, [1, 3]], 0.0, float(original_height))
    return mapped


def _nms_indices(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    if boxes.size == 0:
        return []
    order = np.argsort(-scores)
    keep: list[int] = []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    while order.size > 0:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[current], x1[rest])
        yy1 = np.maximum(y1[current], y1[rest])
        xx2 = np.minimum(x2[current], x2[rest])
        yy2 = np.minimum(y2[current], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[current] + areas[rest] - inter
        iou = np.divide(inter, np.maximum(union, 1e-6))
        order = rest[iou <= iou_threshold]
    return keep


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_hailo_architecture() -> str:
    try:
        result = subprocess.run(["hailortcli", "fw-control", "identify"], capture_output=True, text=True, timeout=5)
    except Exception:
        return "unknown"
    output = result.stdout + result.stderr
    for line in output.splitlines():
        if "Device Architecture:" in line:
            return line.split(":", 1)[1].strip()
    return "unknown"


def detect_hailo_device() -> str:
    try:
        result = subprocess.run(["hailortcli", "scan"], capture_output=True, text=True, timeout=5)
    except Exception:
        return "unknown"
    output = result.stdout + result.stderr
    for line in output.splitlines():
        stripped = line.strip()
        if "Device:" in stripped:
            return stripped
    for line in output.splitlines():
        stripped = line.strip()
        if stripped and stripped != "Hailo Devices:":
            return stripped
    return "unknown"


def map_hef_outputs_to_onnx_inputs(outputs: dict[str, np.ndarray], tensor_mapping: dict) -> dict[str, np.ndarray]:
    onnx_inputs: dict[str, np.ndarray] = {}
    for hef_name, (onnx_name, expected_shape) in tensor_mapping.items():
        if hef_name not in outputs:
            raise HailoUnavailableError(f"Expected HEF output '{hef_name}' not found. Available: {list(outputs)}")
        tensor = np.asarray(outputs[hef_name])
        if tensor.ndim == 3:
            tensor = tensor[np.newaxis, ...]
        actual = list(tensor.shape)
        if len(actual) != 4:
            raise HailoUnavailableError(f"Unexpected HEF output shape for '{hef_name}': {tensor.shape}")
        if actual[1:] == expected_shape:
            mapped = tensor
        elif [actual[3], actual[1], actual[2]] == expected_shape:
            mapped = np.transpose(tensor, (0, 3, 1, 2))
        else:
            raise HailoUnavailableError(
                f"Shape mismatch for '{hef_name}': expected {expected_shape}, got {actual[1:]} full={tensor.shape}"
            )
        if mapped.dtype != np.float32:
            mapped = mapped.astype(np.float32, copy=False)
        onnx_inputs[onnx_name] = mapped
    return onnx_inputs
