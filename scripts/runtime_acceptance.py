#!/usr/bin/env python3
"""Read-only acceptance monitor: no images, credentials, restart or deployment."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from scripts.status_api import counting_readiness  # noqa: E402
from visitor_counter.configuration import load_config  # noqa: E402
from visitor_counter.live_person_count import live_person_count  # noqa: E402
from visitor_counter.runtime_paths import RuntimePaths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 1800:
        parser.error("seconds must be between 0 and 1800")
    paths = RuntimePaths.discover(args.project_root)
    config = load_config(paths.config_file)
    deadline = time.monotonic() + args.seconds
    all_ready = True
    while True:
        try:
            live = json.loads(paths.live_status_file.read_text(encoding="utf-8"))
            age = time.time() - float(live.get("timestamp", 0))
            if not 0 <= age < 10:
                live = None
        except (OSError, ValueError, TypeError):
            live = None
        readiness = counting_readiness(live, config)
        all_ready &= readiness["state"] == "ready"
        print(json.dumps({"timestamp": time.time(), "readiness": readiness,
                          "live_people": asdict(live_person_count(live)),
                          "counts": (live or {}).get("counts", {}),
                          "classification": "LIVE_OBSERVATION; controlled passages NOT TESTED"}), flush=True)
        if time.monotonic() >= deadline:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    database = Path(config.database.path).expanduser()
    database = database if database.is_absolute() else paths.project_root / database
    if database.exists():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        print(json.dumps({"database_integrity": integrity}))
        all_ready &= integrity == "ok"
    else:
        all_ready = False
    return 0 if all_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
