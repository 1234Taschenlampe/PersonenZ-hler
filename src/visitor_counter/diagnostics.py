from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import zipfile
from pathlib import Path
from time import time
from typing import Any

import psutil

from .camera_manager import discover_cameras
from .configuration import load_config
from .model_manager import ModelManager
from .reid_manager import OSNetReIDManager

_SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|token|secret|private.?key|credential|authorization)"
)
_URL_CREDENTIAL = re.compile(r"(?i)(rtsp|rtsps|https?)://([^:/\s]+):([^@/\s]+)@")
_BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+")


def redact_sensitive(value: Any, key: str = "") -> Any:
    """Recursively remove credentials while preserving useful diagnostics."""
    if _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(item_key): redact_sensitive(item, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        value = _URL_CREDENTIAL.sub(r"\1://<redacted>@", value)
        return _BEARER.sub("Bearer <redacted>", value)
    return value


def _run(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=10
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
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


def collect_diagnostics(
    project_root: Path,
    *,
    config_file: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    report = {
        "timestamp": time(),
        "platform": os.name,
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "cameras": discover_cameras(),
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "ram_percent": psutil.virtual_memory().percent,
        "temperature_c": read_pi_temperature_c(),
        "hailortcli": _run(["hailortcli", "fw-control", "identify"]),
        "hailort_version": _run(["hailortcli", "--version"]),
        "v4l2_devices": _run(["v4l2-ctl", "--list-devices"]),
    }
    try:
        config = load_config(config_file or project_root / "config" / "config.yaml")
        detector = ModelManager(config.model, project_root).status()
        reid = OSNetReIDManager(config.model, project_root).status(validate_hailo=False)
        report["detector"] = {
            "name": detector.name,
            "path": str(detector.path),
            "exists": detector.exists,
            "sha256": detector.sha256,
            "message": detector.message,
        }
        report["reid"] = {
            "name": reid.name,
            "path": str(reid.path),
            "exists": reid.exists,
            "ready": reid.ready,
            "sha256": reid.sha256,
            "message": reid.message,
        }
    except (OSError, TypeError, ValueError) as exc:
        report["models_error"] = str(exc)
    output = (output_dir or project_root / "logs") / "diagnostics_report.json"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError:
        # Installed GUI users can inspect hardware without write access to the
        # service-owned log directory. The report is still returned/exported.
        pass
    return report


def create_diagnostic_bundle(
    project_root: Path,
    destination: Path,
    *,
    config_file: Path | None = None,
    log_dir: Path | None = None,
) -> Path:
    """Create a redacted support ZIP without images, databases or secrets."""
    report = redact_sensitive(
        collect_diagnostics(project_root, config_file=config_file, output_dir=log_dir)
    )
    config_path = config_file or project_root / "config" / "config.yaml"
    logs = log_dir or project_root / "logs"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostics/system.json", json.dumps(report, indent=2, ensure_ascii=False)
        )
        if config_path.is_file() and not config_path.is_symlink():
            try:
                import yaml

                raw_config = (
                    yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                )
                sanitized = redact_sensitive(raw_config)
                archive.writestr(
                    "diagnostics/config.redacted.yaml",
                    yaml.safe_dump(sanitized, sort_keys=False),
                )
            except (OSError, ValueError):
                archive.writestr(
                    "diagnostics/config-error.txt",
                    "Konfiguration konnte nicht redigiert gelesen werden.",
                )
        if logs.is_dir():
            for path in sorted(logs.glob("*.log"))[:10]:
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_size > 5_000_000
                ):
                    continue
                try:
                    tail = path.read_text(encoding="utf-8", errors="replace")[-200_000:]
                except OSError:
                    continue
                archive.writestr(
                    f"diagnostics/logs/{path.name}", str(redact_sensitive(tail))
                )
        archive.writestr(
            "diagnostics/README.txt",
            "Dieses Paket enthält keine Datenbank, keine Bilder und keine absichtlich exportierten Secrets.\n",
        )
    temporary.replace(destination)
    return destination
