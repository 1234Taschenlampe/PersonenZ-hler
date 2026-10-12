#!/usr/bin/env python3
"""Opt-in physical Hailo test of an operator-provided recorded video.

Never stops production or writes a database, embedding, image or video. This
proves inference on recorded input, not actual live entry/exit ground truth.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visitor_counter.configuration import load_config  # noqa: E402
from visitor_counter.runtime_paths import RuntimePaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--hardware-test", action="store_true", required=True)
    args = parser.parse_args()
    if not 1 <= args.frames <= 10000:
        parser.error("frames must be between 1 and 10000")
    if hashlib.sha256(args.video.read_bytes()).hexdigest() != args.sha256.lower():
        raise SystemExit("Video checksum mismatch")
    # Refuse contention with either installation type. An inaccessible bus also
    # fails closed, since that is not evidence that hardware is free.
    for scope in (["--user"], []):
        state = subprocess.run(["systemctl", *scope, "is-active", "personenzaehler.service"], capture_output=True, text=True, timeout=10)
        if state.returncode not in {3, 4}:
            raise SystemExit("Stop/verify the production pipeline explicitly before this hardware test")
    import cv2
    import numpy as np
    from visitor_counter.hailo_manager import HailoManager
    from visitor_counter.reid_manager import OSNetReIDManager
    from visitor_counter.tracker import create_tracker
    paths = RuntimePaths.discover(args.project_root)
    config = load_config(paths.config_file)
    hef = Path(config.model.hef_path).expanduser()
    detector = HailoManager(config.model, hef if hef.is_absolute() else paths.project_root / hef)
    reid = OSNetReIDManager(config.model, paths.project_root)
    tracker, actual_tracker = create_tracker(config.tracking)
    capture = cv2.VideoCapture(str(args.video))
    frames = maximum = tracked = embeddings = 0
    try:
        detector.initialize()
        reid.initialize()
        if not detector.ready or not reid.ready:
            raise RuntimeError("Real Hailo detector/ReID unavailable")
        for _ in range(args.frames):
            ok, image = capture.read()
            if not ok:
                break
            detections = detector.infer(image)
            assert all(d.class_id == 0 and d.label == "person" for d in detections)
            tracks = tracker.update("recorded_video", detections)
            maximum = max(maximum, len(detections))
            tracked = max(tracked, sum(t.confirmed and t.lost_frames == 0 for t in tracks))
            if len(detections) >= 2 and embeddings < 6:
                for detection in detections[:2]:
                    embedding = reid.infer_embedding(image, detection.bbox)
                    assert embedding is not None and len(embedding) == 512
                    assert abs(float(np.linalg.norm(embedding)) - 1) < 1e-4
                    embeddings += 1
            frames += 1
    finally:
        capture.release()
        detector.close()
        reid.close()
    passed = maximum >= 2 and tracked >= 2 and embeddings >= 2
    print(json.dumps({"classification": "RECORDED_VIDEO_ON_PHYSICAL_HAILO; live passages NOT TESTED",
                      "frames": frames, "maximum_person_detections": maximum,
                      "maximum_confirmed_tracks": tracked, "actual_tracker": actual_tracker,
                      "validated_osnet_embeddings": embeddings, "passed": passed}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
