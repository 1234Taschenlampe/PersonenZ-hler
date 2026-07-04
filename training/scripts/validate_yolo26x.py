from __future__ import annotations

import argparse
from pathlib import Path

from common import sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a trained YOLO26x person model.")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("training/dataset/dataset.yaml"))
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()
    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    metrics = model.val(data=str(args.data), imgsz=args.imgsz, split="val")
    report = {"created_at": utc_now(), "weights": str(args.weights), "weights_sha256": sha256_file(args.weights), "metrics": str(metrics)}
    write_json(Path("reports") / "yolo26x_validation.json", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
