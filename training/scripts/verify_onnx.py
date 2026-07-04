from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import onnx
import onnxruntime as ort

from common import sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ONNX checker, shape inference and runtime output.")
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/onnx_verification.json"))
    args = parser.parse_args()
    model = onnx.load(str(args.onnx))
    onnx.checker.check_model(model)
    inferred = onnx.shape_inference.infer_shapes(model)
    sess = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    image = cv2.imread(str(args.image))
    if image is None:
        raise RuntimeError(f"Cannot read image: {args.image}")
    size = sess.get_inputs()[0].shape[-1]
    resized = cv2.resize(image, (size, size))
    tensor = resized[:, :, ::-1].transpose(2, 0, 1).astype(np.float32)[None] / 255.0
    outputs = sess.run(None, {sess.get_inputs()[0].name: tensor})
    report = {
        "created_at": utc_now(),
        "onnx": str(args.onnx),
        "onnx_sha256": sha256_file(args.onnx),
        "inputs": [{"name": item.name, "shape": item.shape} for item in sess.get_inputs()],
        "outputs": [{"name": item.name, "shape": item.shape} for item in sess.get_outputs()],
        "runtime_output_shapes": [list(output.shape) for output in outputs],
        "shape_inference_outputs": len(inferred.graph.output),
    }
    write_json(args.report, report)
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
