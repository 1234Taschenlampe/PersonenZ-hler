from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import psutil  # noqa: E402

from visitor_counter.configuration import load_config  # noqa: E402
from visitor_counter.diagnostics import read_pi_temperature_c  # noqa: E402
from visitor_counter.model_manager import ModelManager  # noqa: E402
from visitor_counter.reid_manager import OSNetReIDManager  # noqa: E402


def build_status(project_root: Path) -> dict:
    config = load_config(project_root / "config" / "config.yaml")
    detector = ModelManager(config.model, project_root).status()
    reid = OSNetReIDManager(config.model, project_root).status(validate_hailo=False)
    return {
        "timestamp": time(),
        "service": "visitor-counter",
        "detector": {
            "configured_model": config.model.model_name,
            "active": detector.active_model_name is not None,
            "hef": str(detector.path),
            "hef_exists": detector.exists,
            "hef_sha256": detector.sha256,
            "target": str(detector.target_path),
            "target_exists": detector.target_exists,
            "message": detector.message,
            "error": detector.error_message,
            "fallback_enabled": config.model.allow_fallback or config.model.detector_fallback_enabled,
            "class_filter": {"0": "person"},
        },
        "reid": {
            "configured_model": config.model.reid_model_name,
            "hef": str(reid.path),
            "ready": reid.ready,
            "sha256": reid.sha256,
            "message": reid.message,
        },
        "hailo": _hailo_status(),
        "host": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "swap_percent": psutil.swap_memory().percent,
            "disk_free_bytes": shutil.disk_usage(project_root).free,
            "load_average": list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [],
            "temperature_c": read_pi_temperature_c(),
        },
        "database": _database_status(project_root / config.database.path),
    }


def _hailo_status() -> dict:
    scan = _run(["hailortcli", "scan"])
    identify = _run(["hailortcli", "fw-control", "identify"])
    return {
        "scan": scan,
        "identify": identify,
        "device_detected": "Device:" in scan,
        "architecture": "HAILO10H" if "HAILO10H" in identify else "unknown",
    }


def _database_status(path: Path) -> dict:
    wal = Path(str(path) + "-wal")
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "wal_size_bytes": wal.stat().st_size if wal.exists() else 0,
    }


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return (result.stdout + result.stderr).strip()


class StatusHandler(BaseHTTPRequestHandler):
    project_root = PROJECT_ROOT

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] in {"/health", "/status"}:
            status = build_status(self.project_root)
            code = 200 if status["hailo"]["device_detected"] else 503
            self._send_json(code, status)
            return
        if self.path.split("?", 1)[0] == "/metrics":
            status = build_status(self.project_root)
            lines = [
                f"visitor_counter_hailo_device_detected {1 if status['hailo']['device_detected'] else 0}",
                f"visitor_counter_detector_hef_exists {1 if status['detector']['hef_exists'] else 0}",
                f"visitor_counter_reid_ready {1 if status['reid']['ready'] else 0}",
                f"visitor_counter_host_cpu_percent {status['host']['cpu_percent']}",
                f"visitor_counter_host_ram_percent {status['host']['ram_percent']}",
                f"visitor_counter_database_size_bytes {status['database']['size_bytes']}",
            ]
            body = "\n".join(lines) + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        self._send_json(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local visitor-counter status API.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    StatusHandler.project_root = args.project_root.resolve()
    server = ThreadingHTTPServer((args.host, args.port), StatusHandler)
    print(f"status API listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
