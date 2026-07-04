from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--har", type=Path, default=Path("models/yolo26x_optimized.har"))
    parser.add_argument("--hef", type=Path, default=Path("models/yolo26x_hailo10h_640.hef"))
    args = parser.parse_args()
    args.hef.parent.mkdir(parents=True, exist_ok=True)
    command = ["hailomz", "compile", "--har", str(args.har), "--hef-path", str(args.hef)]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
