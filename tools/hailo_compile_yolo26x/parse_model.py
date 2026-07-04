from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", type=Path, default=Path("models/yolo26x.onnx"))
    parser.add_argument("--yaml", type=Path, default=Path("tools/hailo_compile_yolo26x/yolo26x.yaml"))
    parser.add_argument("--har", type=Path, default=Path("models/yolo26x.har"))
    args = parser.parse_args()
    command = [
        "hailomz",
        "parse",
        "--ckpt",
        str(args.onnx),
        "--yaml",
        str(args.yaml),
        "--har-path",
        str(args.har),
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
