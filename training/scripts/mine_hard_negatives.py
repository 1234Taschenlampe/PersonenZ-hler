from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from common import require_privacy_approval, secure_directory, secure_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a model over video/images and collect candidate hard negatives for manual review.")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--privacy-approval", type=Path, required=True)
    args = parser.parse_args()
    require_privacy_approval(args.privacy_approval)
    from ultralytics import YOLO

    secure_directory(args.output)
    model = YOLO(str(args.weights))
    saved: list[dict] = []
    for result in model.predict(source=str(args.source), conf=args.confidence, stream=True, classes=[0]):
        image = result.orig_img
        if image is None:
            continue
        if len(result.boxes or []) > 0:
            path = args.output / f"candidate_{len(saved):06d}.jpg"
            cv2.imwrite(str(path), image)
            secure_file(path)
            saved.append({"file": path.name, "boxes": len(result.boxes)})
    write_json(args.output / "hard_negative_manifest.json", {"created_at": utc_now(), "items": saved})
    print(f"candidates={len(saved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
