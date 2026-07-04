from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--har", type=Path, default=Path("models/yolo26x.har"))
    parser.add_argument("--calib-path", type=Path, required=True)
    parser.add_argument("--alls", type=Path, default=Path("tools/hailo_compile_yolo26x/yolo26x_hailo10h.alls"))
    parser.add_argument("--output", type=Path, default=Path("models/yolo26x_optimized.har"))
    args = parser.parse_args()
    command = [
        "hailomz",
        "optimize",
        "--har",
        str(args.har),
        "--calib-path",
        str(args.calib_path),
        "--model-script",
        str(args.alls),
        "--output-har-path",
        str(args.output),
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
