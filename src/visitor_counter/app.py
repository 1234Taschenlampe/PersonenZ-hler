from __future__ import annotations

import argparse
from pathlib import Path

from .gui import run_gui


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLO26x dual-camera visitor counter")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    return run_gui(args.project_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
