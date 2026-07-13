from __future__ import annotations

import argparse
from pathlib import Path
from time import monotonic, sleep, time

import cv2

from common import require_privacy_approval, secure_directory, secure_file, utc_now, write_json


def capture(camera: str, output_dir: Path, camera_id: str, scenario: str, seconds: float, fps: float) -> dict:
    cap = cv2.VideoCapture(camera, cv2.CAP_V4L2)
    secure_directory(output_dir)
    manifest: list[dict] = []
    if not cap.isOpened():
        return {"camera_id": camera_id, "camera": camera, "error": "open failed", "frames": 0}
    interval = 1.0 / max(fps, 0.1)
    started = monotonic()
    next_frame = started
    frame_id = 0
    try:
        while monotonic() - started < seconds:
            ok, frame = cap.read()
            now = monotonic()
            if not ok or frame is None:
                sleep(0.1)
                continue
            if now < next_frame:
                continue
            frame_id += 1
            timestamp = time()
            name = f"{camera_id}_{scenario}_{int(timestamp * 1000)}_{frame_id:06d}.jpg"
            path = output_dir / name
            cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            secure_file(path)
            manifest.append(
                {
                    "file": str(path),
                    "camera_id": camera_id,
                    "scenario": scenario,
                    "timestamp": timestamp,
                    "utc": utc_now(),
                    "width": int(frame.shape[1]),
                    "height": int(frame.shape[0]),
                }
            )
            next_frame = now + interval
    finally:
        cap.release()
    return {"camera_id": camera_id, "camera": camera, "frames": frame_id, "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture timestamped frames from the two real cameras.")
    parser.add_argument("--camera-1", required=True)
    parser.add_argument("--camera-2", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--privacy-approval", type=Path, required=True)
    args = parser.parse_args()
    approval = require_privacy_approval(args.privacy_approval)
    session_dir = args.output / f"{utc_now().replace(':', '').replace('+', 'Z')}_{args.scenario}"
    secure_directory(session_dir)
    results = [
        capture(args.camera_1, session_dir / "camera_1", "camera_1", args.scenario, args.seconds, args.fps),
        capture(args.camera_2, session_dir / "camera_2", "camera_2", args.scenario, args.seconds, args.fps),
    ]
    flat = [item for result in results for item in result.get("manifest", [])]
    write_json(
        session_dir / "capture_manifest.json",
        {
            "created_at": utc_now(),
            "scenario": args.scenario,
            "privacy_approval": {
                "purpose": approval["purpose"],
                "controller": approval["controller"],
                "expires_at": approval["expires_at"],
            },
            "results": results,
            "items": flat,
        },
    )
    print(session_dir)
    return 0 if all("error" not in result for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
