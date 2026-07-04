from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from time import time
from typing import Any

import psutil

from .camera_manager import discover_cameras


def _run(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
        return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except Exception as exc:  # noqa: BLE001
        return {"command": command, "error": str(exc)}


def read_pi_temperature_c() -> float | None:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip()) / 1000.0
    except ValueError:
        return None


def collect_diagnostics(project_root: Path) -> dict[str, Any]:
    report = {
        "timestamp": time(),
        "platform": os.name,
        "cameras": discover_cameras(),
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "ram_percent": psutil.virtual_memory().percent,
        "temperature_c": read_pi_temperature_c(),
        "hailortcli": _run(["hailortcli", "fw-control", "identify"]),
        "hailort_version": _run(["hailortcli", "--version"]),
        "v4l2_devices": _run(["v4l2-ctl", "--list-devices"]),
    }
    output = project_root / "logs" / "diagnostics_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
