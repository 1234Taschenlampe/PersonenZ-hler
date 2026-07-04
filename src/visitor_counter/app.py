from __future__ import annotations

import argparse
from pathlib import Path

from .gui import run_gui
from .synthetic_test import run_synthetic_counter_test


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLO26m dual-camera visitor counter")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--test-global-counter", action="store_true", help="Run the synthetic global counter validation test")
    args = parser.parse_args()
    
    project_root = args.project_root.resolve()
    if args.test_global_counter:
        return run_synthetic_counter_test(project_root)
        
    return run_gui(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
