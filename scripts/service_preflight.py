#!/usr/bin/env python3
"""Return systemd ExecCondition readiness; 1 skips (without restart storms).

This checks only prerequisites visible on disk. A successful check is NOT a
hardware acceptance test, license check or proof that RTSP is reachable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visitor_counter.configuration import load_config, validate_config  # noqa: E402
from visitor_counter.runtime_paths import RuntimePaths  # noqa: E402


def ready(root: Path, config_file: Path) -> tuple[bool, str]:
    if not config_file.is_file() or config_file.is_symlink():
        return False, "Konfiguration fehlt"
    try:
        config = load_config(config_file)
        errors = validate_config(config)
        if errors:
            return False, "Konfiguration ungültig: " + errors[0]
        if not any(camera.device for camera in config.cameras.values()):
            return False, "Kameraquellen noch nicht konfiguriert"
        paths = (
            (
                config.model.hef_path,
                config.model.reid_hef_path if config.model.reid_required else None,
                config.model.postprocess_onnx_path,
                config.model.postprocess_config_path,
            )
            if config.model.detector_enabled
            else ()
        )
        for name in paths:
            if not name:
                continue
            path = Path(name).expanduser()
            if not path.is_absolute():
                path = root / path
            if path.is_symlink() or not path.is_file() or path.stat().st_size < 1:
                return False, f"Modell/Verarbeitung fehlt: {path.name}"
        return True, "Dateivoraussetzungen erfüllt; Runtime-Test steht aus"
    except (OSError, ValueError, TypeError) as exc:
        return False, f"Konfiguration nicht lesbar: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    paths = RuntimePaths.discover(args.project_root)
    ok, detail = ready(paths.project_root, paths.config_file)
    print(detail, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
