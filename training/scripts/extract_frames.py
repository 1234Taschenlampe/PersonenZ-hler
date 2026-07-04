from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from common import utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract sparse frames from videos without high-frequency leakage.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.input))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {args.input}")
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(video_fps * args.interval_seconds))
    index = 0
    saved = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % step == 0:
            path = args.output / f"{args.input.stem}_{index:08d}.jpg"
            cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            saved.append({"file": str(path), "source": str(args.input), "frame_index": index, "camera_id": args.camera_id, "scenario": args.scenario})
        index += 1
    cap.release()
    write_json(args.output / "extract_manifest.json", {"created_at": utc_now(), "items": saved})
    print(f"saved={len(saved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
