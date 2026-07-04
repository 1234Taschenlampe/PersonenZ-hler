from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from common import utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a model over video/images and collect candidate hard negatives for manual review.")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/home/raspibob/person_dataset_raw/hard_negative_candidates"))
    parser.add_argument("--confidence", type=float, default=0.25)
    args = parser.parse_args()
    from ultralytics import YOLO

    args.output.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.weights))
    saved: list[dict] = []
    for result in model.predict(source=str(args.source), conf=args.confidence, stream=True, classes=[0]):
        image = result.orig_img
        if image is None:
            continue
        if len(result.boxes or []) > 0:
            path = args.output / f"candidate_{len(saved):06d}.jpg"
            cv2.imwrite(str(path), image)
            saved.append({"file": str(path), "boxes": len(result.boxes), "source": str(args.source)})
    write_json(args.output / "hard_negative_manifest.json", {"created_at": utc_now(), "items": saved})
    print(f"candidates={len(saved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
