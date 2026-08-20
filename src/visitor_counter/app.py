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
    except Exception as exc:
        return f"error_{exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLO26m dual-camera visitor counter")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--test-global-counter",
        action="store_true",
        help="Run the synthetic global counter validation test",
    )
    parser.add_argument(
        "--system-layout",
        action="store_true",
        help="Use /etc, /var/lib, /var/log and /var/cache installation paths",
    )
    parser.add_argument(
        "--no-wizard",
        action="store_true",
        help="Do not open the first-run wizard automatically",
    )
    parser.add_argument(
        "--legacy-embedded",
        action="store_true",
        help="Run the legacy embedded camera GUI (development only)",
    )
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
    if args.legacy_embedded:
        from .license_guard import LicenseError, enforce_license

        try:
            enforce_license(project_root)
        except LicenseError as exc:
            print(f"Start blockiert: {exc}")
            return 4
        from . import gui as gui_module
        from .enhanced_counting import EnhancedProcessingPipeline, install_enhanced_gui

        gui_module.ProcessingPipeline = EnhancedProcessingPipeline
        install_enhanced_gui(gui_module)
        return gui_module.run_gui(project_root)

    from .desktop import run_desktop
    from .runtime_paths import RuntimePaths

    paths = RuntimePaths.discover(project_root, system_layout=args.system_layout)
    return run_desktop(paths, show_wizard=not args.no_wizard)


if __name__ == "__main__":
    raise SystemExit(main())
