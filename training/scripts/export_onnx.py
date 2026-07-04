from __future__ import annotations

import argparse
from pathlib import Path

from common import sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Export trained person-only YOLO26x checkpoint to static ONNX.")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--opset", type=int, default=11)
    parser.add_argument("--output", type=Path, default=Path("training/exports/yolo26x_person_640.onnx"))
    args = parser.parse_args()
    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    exported = Path(model.export(format="onnx", imgsz=args.imgsz, opset=args.opset, dynamic=False, batch=1, simplify=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if exported.resolve() != args.output.resolve():
        exported.replace(args.output)
    write_json(
        args.output.with_suffix(".manifest.json"),
        {"created_at": utc_now(), "weights": str(args.weights), "weights_sha256": sha256_file(args.weights), "onnx": str(args.output), "onnx_sha256": sha256_file(args.output), "imgsz": args.imgsz, "opset": args.opset},
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
