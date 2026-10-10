"""Run the deployed detector on a local, nonprivate image without saving pixels.

Example (from the checkout, with its Pi virtual environment active)::

    PYTHONPATH=src python scripts/verify_hailo_detection.py \
        --config config/config.yaml --image /tmp/public-person.jpg --require-person --reid

This is an inference smoke check, not a camera, tracking or passage test.
No camera connection, database write, image export or external API is used.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from visitor_counter.configuration import AppConfig, load_config
from visitor_counter.hailo_manager import HailoManager
from visitor_counter.model_manager import ModelManager
from visitor_counter.reid_manager import OSNetReIDManager


class ObservedHailoManager(HailoManager):
    """Record tensor metadata while using the unchanged production decoder."""

    def _decode_outputs(self, outputs, original_width, original_height):
        self.output_shapes = {name: list(np.asarray(value).shape) for name, value in outputs.items()}
        return super()._decode_outputs(outputs, original_width, original_height)


def verify_image(config: AppConfig, project_root: Path, image: np.ndarray, *, runs: int = 3, reid: bool = False) -> dict:
    if runs < 1 or runs > 100:
        raise ValueError("runs must be between 1 and 100")
    detector = ObservedHailoManager(config.model, ModelManager(config.model, project_root).hef_path)
    reid_manager = None
    try:
        detector.initialize()
        tensor, _ = detector._preprocess(image)
        if tensor.shape != (1, 640, 640, 3) or tensor.dtype != np.uint8:
            raise ValueError("YOLO26m requires RGB UINT8 640x640 input")
        infer_model = detector._infer_model
        report = {
            "native_width": int(image.shape[1]),
            "native_height": int(image.shape[0]),
            "input_shape": list(tensor.shape),
            "hef_input_shape": list(infer_model.input().shape),
            "input_color": "RGB",
            "input_dtype": str(tensor.dtype),
            "hef_sha256": detector.hef_sha256,
            "hailo_architecture": detector.hailo_architecture,
            "postprocess": "ONNX" if detector._onnx_session is not None else "native",
            "confidence_threshold": config.model.confidence_threshold,
            "runs": [],
        }
        if config.model.output_format == "yolo26_detection" and detector._onnx_session is None:
            raise RuntimeError("YOLO26 detection ONNX postprocess is not active")
        last_detections = []
        for _ in range(runs):
            start = perf_counter()
            last_detections = detector.infer(image)
            report["runs"].append({
                "total_ms": (perf_counter() - start) * 1000,
                "hailo_ms": detector.last_latency_ms,
                "stages_ms": dict(detector.last_stage_ms),
                "persons": [{
                    "confidence": float(d.confidence),
                    "box_xyxy": [float(d.bbox.x1), float(d.bbox.y1), float(d.bbox.x2), float(d.bbox.y2)],
                } for d in last_detections],
            })
        report["output_shapes"] = detector.output_shapes
        report["inference_count"] = detector.inference_count
        report["person_detected_each_run"] = all(bool(run["persons"]) for run in report["runs"])
        if reid:
            report["reid"] = {"attempted": False, "reason": "no detected person"}
            if last_detections:
                reid_manager = OSNetReIDManager(config.model, project_root)
                try:
                    reid_manager.initialize()
                    embedding = reid_manager.infer_embedding(image, last_detections[0].bbox)
                    report["reid"] = {
                        "attempted": True,
                        "valid": embedding is not None,
                        "dimension": len(embedding) if embedding is not None else None,
                        "embedding_norm": float(np.linalg.norm(embedding)) if embedding is not None else None,
                        "latency_ms": reid_manager.last_latency_ms,
                        "error_count": reid_manager.error_count,
                    }
                except Exception as exc:
                    report["reid"] = {"attempted": True, "valid": False, "error_type": type(exc).__name__}
        return report
    finally:
        if reid_manager is not None:
            reid_manager.close()
        detector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify actual Hailo/ONNX detection using a local public or nonprivate image; never writes images.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--require-person", action="store_true", help="Fail if any inference run has no person detection")
    parser.add_argument("--reid", action="store_true", help="Also check OSNet using the first detected person; never prints its vector")
    args = parser.parse_args(argv)
    # Keep third-party/production logger messages out of this metadata-only report.
    logging.disable(logging.CRITICAL)
    try:
        image_path = args.image.resolve(strict=True)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode local image")
        config = load_config(args.config)
        report = verify_image(config, args.project_root.resolve(), image, runs=args.runs, reid=args.reid)
        report["passed"] = (not args.require_person or report["person_detected_each_run"]) and (
            not args.reid or report.get("reid", {}).get("valid", False)
        )
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["passed"] else 2
    except Exception as exc:
        # File names/configuration contents/credentials/pixels are never printed.
        print(json.dumps({"passed": False, "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
