#!/usr/bin/env python3
"""No-op unless private camera-addresses.json exists; --apply enables recovery."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visitor_counter.camera_address_recovery import recover  # noqa: E402
from visitor_counter.runtime_paths import RuntimePaths  # noqa: E402


def main() -> int:
    import fcntl  # Linux timer; pure functions remain portable for unit tests.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    paths = RuntimePaths.discover(args.project_root)
    pins = paths.config_file.parent / "camera-addresses.json"
    if not pins.exists():
        return 0
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (paths.state_dir / "camera-address-guard.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        recover(paths.config_file, pins, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
