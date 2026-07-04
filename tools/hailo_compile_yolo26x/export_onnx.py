from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=Path, default=Path("models/yolo26x.pt"))
    parser.add_argument("--output-dir", type=Path, default=Path("models"))
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.weights))
    exported = model.export(format="onnx", imgsz=args.imgsz, batch=1, dynamic=False, simplify=True, opset=17)
    output = args.output_dir / "yolo26x.onnx"
    Path(exported).replace(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
