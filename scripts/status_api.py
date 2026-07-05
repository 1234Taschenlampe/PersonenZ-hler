from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import time
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import psutil  # noqa: E402

from visitor_counter.configuration import load_config  # noqa: E402
from visitor_counter.database import EventDatabase  # noqa: E402
from visitor_counter.diagnostics import read_pi_temperature_c  # noqa: E402
from visitor_counter.model_manager import ModelManager  # noqa: E402
from visitor_counter.reid_manager import OSNetReIDManager  # noqa: E402


def build_status(project_root: Path) -> dict:
    config = load_config(project_root / "config" / "config.yaml")
    detector = ModelManager(config.model, project_root).status()
    reid = OSNetReIDManager(config.model, project_root).status(validate_hailo=False)
    db_path = project_root / config.database.path
    counts = _counts_status(db_path)
    cameras = [
        {
            "camera_id": camera.camera_id,
            "name": camera.display_name,
            "role": camera.role,
            "source": "USB" if camera.device else None,
            "device": camera.device,
            "wanted_fps": camera.fps,
            "width": camera.width,
            "height": camera.height,
            "status": "UNKNOWN",
            "actual_fps": None,
            "last_frame_time": None,
            "seconds_since_last_frame": None,
            "connected_seconds": None,
            "reconnect_count": None,
            "dropped_frames": None,
            "decode_errors": None,
            "last_error": None,
            "visible": None,
            "entered": None,
            "exited": None,
        }
        for camera in config.cameras.values()
    ]
    return {
        "timestamp": time(),
        "service": "visitor-counter",
        "version": _version(project_root),
        "api": {
            "name": "visitor-counter-status-api",
            "version": "1",
            "pairing": "not_available",
            "websocket": "not_available",
        },
        "counts": counts,
        "cameras": cameras,
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
            "system_uptime_seconds": _system_uptime_seconds(),
        },
        "database": _database_status(db_path),
    }


def _version(project_root: Path) -> dict:
    commit = _run(["git", "-C", str(project_root), "rev-parse", "--short", "HEAD"])
    return {
        "server": "visitor-counter",
        "git_commit": commit if commit and "fatal:" not in commit.lower() else None,
    }


def _system_uptime_seconds() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except Exception:  # noqa: BLE001
        return None


def _counts_status(path: Path) -> dict:
    if not path.exists():
        return {
            "inside": None,
            "entered": None,
            "exited": None,
            "visible": None,
            "suppressed": None,
            "uncertain": None,
            "last_event_time": None,
        }
    db = EventDatabase(path)
    try:
        counts = db.restore_counts()
        last_event = db._connection.execute(  # noqa: SLF001 - status endpoint is read-only diagnostics
            "SELECT timestamp FROM counting_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return {
            "inside": counts.get("inside"),
            "entered": counts.get("entered"),
            "exited": counts.get("exited"),
            "visible": None,
            "suppressed": counts.get("suppressed"),
            "uncertain": counts.get("uncertain"),
            "last_event_time": None if not last_event else last_event[0],
        }
    finally:
        db.close()


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
        parsed = urlparse(self.path)
        route = parsed.path
        if route in {"/health", "/status", "/api/v1/health", "/api/v1/status"}:
            status = build_status(self.project_root)
            code = 200 if status["hailo"]["device_detected"] else 503
            self._send_json(code, status)
            return
        if route in {"/api/v1/version"}:
            self._send_json(200, build_status(self.project_root)["version"])
            return
        if route in {"/api/v1/counts/current"}:
            self._send_json(200, build_status(self.project_root)["counts"])
            return
        if route in {"/api/v1/telemetry/current"}:
            status = build_status(self.project_root)
            self._send_json(200, {"timestamp": status["timestamp"], "host": status["host"], "hailo": status["hailo"], "database": status["database"]})
            return
        if route in {"/api/v1/cameras"}:
            self._send_json(200, {"cameras": build_status(self.project_root)["cameras"]})
            return
        if route in {"/api/v1/events"}:
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["50"])[0])
            self._send_json(200, {"events": _events(self.project_root, max(1, min(limit, 200)))})
            return
        if route == "/metrics":
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


def _events(project_root: Path, limit: int) -> list[dict]:
    config = load_config(project_root / "config" / "config.yaml")
    path = project_root / config.database.path
    if not path.exists():
        return []
    db = EventDatabase(path)
    try:
        rows = db._connection.execute(  # noqa: SLF001 - status endpoint is read-only diagnostics
            """
            SELECT id, timestamp, camera_id, direction, event_type, counted, uncertain, confidence, consensus_reason
            FROM counting_events
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "event_id": row[0],
                "time": row[1],
                "camera_id": row[2],
                "direction": row[3],
                "event_type": row[4],
                "counted": bool(row[5]),
                "uncertain": bool(row[6]),
                "confidence": row[7],
                "description": row[8],
            }
            for row in rows
        ]
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local visitor-counter status API.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    StatusHandler.project_root = args.project_root.resolve()
    server = ThreadingHTTPServer((args.host, args.port), StatusHandler)
    print(f"status API listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
