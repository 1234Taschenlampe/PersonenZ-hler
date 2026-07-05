from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from .synthetic_test import run_synthetic_counter_test


def get_db_sha256(db_path: Path) -> str:
    if not db_path.exists():
        return "not_exists"
    h = hashlib.sha256()
    try:
        with open(db_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        return f"error_{e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLO26m dual-camera visitor counter")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--test-global-counter", action="store_true", help="Run the synthetic global counter validation test")
    args = parser.parse_args()
    
    project_root = args.project_root.resolve()
    if args.test_global_counter:
        db_path = project_root / "data" / "events.db"
        sha_before = get_db_sha256(db_path)
        print(f"Production database SHA-256 before test: {sha_before}")
        
        result = run_synthetic_counter_test(project_root)
        
        sha_after = get_db_sha256(db_path)
        print(f"Production database SHA-256 after test:  {sha_after}")
        if sha_before == sha_after:
            print("VERIFICATION: Production database remains completely untouched!")
        else:
            print("WARNING: Production database was modified during the test!")
        return result
        
    from .gui import run_gui

    return run_gui(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
