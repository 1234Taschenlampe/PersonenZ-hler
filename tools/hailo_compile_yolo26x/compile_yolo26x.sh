#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
CALIB_PATH="${1:-data/calibration}"
python tools/hailo_compile_yolo26x/export_onnx.py --weights models/yolo26x.pt --output-dir models --imgsz 640
python - <<'PY'
import onnx
model = onnx.load("models/yolo26x.onnx")
onnx.checker.check_model(model)
print("ONNX OK")
print("inputs:", [i.name for i in model.graph.input])
print("outputs:", [o.name for o in model.graph.output])
PY
python tools/hailo_compile_yolo26x/parse_model.py
python tools/hailo_compile_yolo26x/optimize_model.py --calib-path "$CALIB_PATH"
python tools/hailo_compile_yolo26x/compile_hef.py
ls -lh models/yolo26x_hailo10h_640.hef
