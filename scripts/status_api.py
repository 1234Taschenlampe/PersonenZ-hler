from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import select
import shutil
import socket
import ssl
import subprocess
import sys
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import sleep, time
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import psutil  # noqa: E402

from visitor_counter.configuration import AppConfig, load_config  # noqa: E402
from visitor_counter.data_protection import load_data_protector  # noqa: E402
from visitor_counter.database import EventDatabase  # noqa: E402
from visitor_counter.diagnostics import read_pi_temperature_c  # noqa: E402
from visitor_counter.logging_setup import write_audit_event  # noqa: E402
from visitor_counter.model_manager import ModelManager  # noqa: E402
from visitor_counter.privacy import stream_frame_directory  # noqa: E402
from visitor_counter.reid_manager import OSNetReIDManager  # noqa: E402

_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE: tuple[float, dict] | None = None
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {}
ROLE_LEVEL = {"anonymous": 0, "viewer": 1, "operator": 2, "admin": 3}


def _read_live_status(project_root: Path) -> dict | None:
    try:
        live_status_path = project_root / "data" / "live_status.json"
        if not live_status_path.exists():
            return None
        data = json.loads(live_status_path.read_text(encoding="utf-8"))
        age = time() - data.get("timestamp", 0)
        if age > 10.0:
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def build_status(project_root: Path) -> dict:
    config = load_config(project_root / "config" / "config.yaml")
    detector = ModelManager(config.model, project_root).status()
    reid = OSNetReIDManager(config.model, project_root).status(validate_hailo=False)
    db_path = project_root / config.database.path
    live = _read_live_status(project_root)
    if live:
        counts = live.get("counts", _counts_status(project_root, config))
        cameras = [_sanitized_camera_status(item) for item in live.get("cameras", []) if isinstance(item, dict)]
        runtime = dict(live.get("runtime", {}))
        if runtime.get("active_hef"):
            runtime["active_hef"] = Path(str(runtime["active_hef"])).name
    else:
        counts = _counts_status(project_root, config)
        cameras = [
            {
                "camera_id": camera.camera_id,
                "name": camera.display_name,
                "role": camera.role,
                "source": "USB" if camera.device else None,
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
        runtime = {}
    return {
        "timestamp": time(),
        "service": "visitor-counter",
        "version": _version(project_root),
        "live_data_available": live is not None,
        "live_data_age_seconds": round(time() - live["timestamp"], 1) if live else None,
        "api": {
            "name": "visitor-counter-status-api",
            "version": "1",
            "pairing": "not_available",
            "websocket": "/api/v1/ws/live",
            "video": {
                "list": "/api/v1/video",
                "mjpeg": "/api/v1/video/{camera_id}.mjpg",
                "snapshot": "/api/v1/video/{camera_id}/snapshot.jpg",
                "meta": "/api/v1/video/{camera_id}/meta",
            },
        },
        "counts": counts,
        "cameras": cameras,
        "runtime": runtime,
        "detector": {
            "configured_model": config.model.model_name,
            "active": detector.active_model_name is not None,
            "hef": detector.path.name,
            "hef_exists": detector.exists,
            "hef_sha256": detector.sha256,
            "target": detector.target_path.name,
            "target_exists": detector.target_exists,
            "message": _redact_project_path(detector.message, project_root),
            "error": _redact_project_path(detector.error_message, project_root),
            "fallback_enabled": config.model.allow_fallback or config.model.detector_fallback_enabled,
            "class_filter": {"0": "person"},
        },
        "reid": {
            "configured_model": config.model.reid_model_name,
            "hef": reid.path.name,
            "ready": reid.ready,
            "sha256": reid.sha256,
            "message": _redact_project_path(reid.message, project_root),
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


def cached_status(project_root: Path, max_age_seconds: float = 0.75) -> dict:
    global _STATUS_CACHE  # noqa: PLW0603
    now = time()
    with _STATUS_CACHE_LOCK:
        if _STATUS_CACHE and now - _STATUS_CACHE[0] <= max_age_seconds:
            return _STATUS_CACHE[1]
    status = build_status(project_root)
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE = (time(), status)
    return status


def _sanitized_camera_status(item: dict) -> dict:
    allowed = {
        "camera_id", "name", "role", "source", "wanted_fps", "width", "height", "status",
        "actual_fps", "last_frame_time", "seconds_since_last_frame", "connected_seconds",
        "reconnect_count", "dropped_frames", "decode_errors", "visible", "entered", "exited",
    }
    result = {key: value for key, value in item.items() if key in allowed}
    result["last_error"] = None if item.get("status") == "ONLINE" else "camera unavailable"
    return result


def _redact_project_path(value: str | None, project_root: Path) -> str | None:
    if value is None:
        return None
    return value.replace(str(project_root), "<project>")


def _safe_camera_id(camera_id: str) -> str | None:
    camera_id = camera_id.strip()
    if not camera_id:
        return None
    if all(char.isalnum() or char in {"_", "-"} for char in camera_id):
        return camera_id
    return None


def _stream_paths(camera_id: str) -> tuple[Path, Path]:
    stream_dir = stream_frame_directory(StatusHandler.project_root)
    return stream_dir / f"{camera_id}.jpg", stream_dir / f"{camera_id}.json"


def _stream_meta(camera_id: str) -> dict | None:
    jpg_path, meta_path = _stream_paths(camera_id)
    if not jpg_path.exists():
        return None
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}
    stat = jpg_path.stat()
    meta.update(
        {
            "camera_id": camera_id,
            "age_seconds": round(time() - stat.st_mtime, 3),
            "snapshot": f"/api/v1/video/{camera_id}/snapshot.jpg",
            "mjpeg": f"/api/v1/video/{camera_id}.mjpg",
            "meta": f"/api/v1/video/{camera_id}/meta",
        }
    )
    return meta


def _available_streams() -> list[dict]:
    stream_dir = stream_frame_directory(StatusHandler.project_root)
    if not stream_dir.exists():
        return []
    streams: list[dict] = []
    for path in sorted(stream_dir.glob("*.jpg")):
        camera_id = _safe_camera_id(path.stem)
        if camera_id:
            meta = _stream_meta(camera_id)
            if meta:
                streams.append(meta)
    return streams


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


def _counts_status(project_root: Path, config: AppConfig) -> dict:
    path = project_root / config.database.path
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
    db = _open_configured_database(project_root, config)
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
        "device_detected": "Device:" in scan,
        "architecture": "HAILO10H" if "HAILO10H" in identify else "unknown",
    }


def _database_status(path: Path) -> dict:
    wal = Path(str(path) + "-wal")
    return {
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


def _open_configured_database(project_root: Path, config: AppConfig) -> EventDatabase:
    database = config.database
    return EventDatabase(
        project_root / database.path,
        store_personal_events=database.store_events,
        retention_hours=database.retention_hours,
        protector=load_data_protector(database, project_root),
        require_encryption=database.encryption_required,
    )


class StatusHandler(BaseHTTPRequestHandler):
    project_root = PROJECT_ROOT
    app_config = AppConfig()
    tokens: dict[str, str] = {}
    tls_enabled = False
    server_version = "VisitorCounterAPI/1"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        if not self._rate_limit_ok():
            self._audit("rate_limit", "denied", "anonymous", route, 429)
            self._send_json(429, {"error": "rate limit exceeded"})
            return
        if route in {"/health", "/api/v1/health"}:
            self._send_json(200, {"service": "visitor-counter", "status": "available"})
            return
        if route == "/api/v1/privacy/notice":
            privacy = self.app_config.privacy
            self._send_json(
                200,
                {
                    "purpose": privacy.purpose,
                    "legal_basis": privacy.legal_basis or "not documented",
                    "controller": privacy.controller_name or "not documented",
                    "contact": privacy.controller_contact or "not documented",
                    "retention_hours": self.app_config.database.retention_hours,
                    "images_stored": False,
                    "remote_video_enabled": privacy.video_stream_enabled,
                },
            )
            return

        required_role = self._required_role(route)
        role = self._authorize(required_role)
        if role is None:
            self._audit("authorize", "denied", "anonymous", route, 401)
            return
        if route == "/api/v1/ws/live":
            self._handle_websocket()
            return
        if route == "/api/v1/video" or route.startswith("/api/v1/video/"):
            if not self.app_config.privacy.video_stream_enabled:
                self._send_json(404, {"error": "video stream disabled by privacy configuration"})
                return
            if route == "/api/v1/video":
                self._send_json(200, {"streams": _available_streams()})
                return
            if self._handle_video(route, parsed.query):
                return
        if route in {"/status", "/api/v1/status"}:
            status = cached_status(self.project_root)
            self._send_json(200 if status["hailo"]["device_detected"] else 503, status)
            return
        if route == "/api/v1/version":
            self._send_json(200, cached_status(self.project_root)["version"])
            return
        if route == "/api/v1/counts/current":
            self._send_json(200, cached_status(self.project_root)["counts"])
            return
        if route == "/api/v1/telemetry/current":
            status = cached_status(self.project_root)
            self._send_json(200, {"timestamp": status["timestamp"], "host": status["host"], "hailo": status["hailo"], "database": status["database"]})
            return
        if route == "/api/v1/cameras":
            self._send_json(200, {"cameras": cached_status(self.project_root)["cameras"]})
            return
        if route == "/api/v1/runtime":
            status = cached_status(self.project_root)
            self._send_json(200, {"runtime": status.get("runtime", {}), "live_data_available": status.get("live_data_available", False)})
            return
        if route == "/api/v1/events":
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["50"])[0])
            except ValueError:
                self._send_json(400, {"error": "invalid limit"})
                return
            self._send_json(200, {"events": _events(self.project_root, max(1, min(limit, 200)))})
            return
        if route == "/metrics":
            status = cached_status(self.project_root)
            body = "\n".join(
                [
                    f"visitor_counter_hailo_device_detected {1 if status['hailo']['device_detected'] else 0}",
                    f"visitor_counter_detector_hef_exists {1 if status['detector']['hef_exists'] else 0}",
                    f"visitor_counter_reid_ready {1 if status['reid']['ready'] else 0}",
                    f"visitor_counter_host_cpu_percent {status['host']['cpu_percent']}",
                    f"visitor_counter_host_ram_percent {status['host']['ram_percent']}",
                    f"visitor_counter_database_size_bytes {status['database']['size_bytes']}",
                ]
            ) + "\n"
            self._send_bytes(200, body.encode("utf-8"), "text/plain; version=0.0.4")
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if not self._rate_limit_ok():
            self._send_json(429, {"error": "rate limit exceeded"})
            return
        role = self._authorize("admin")
        if role is None:
            self._audit("authorize", "denied", "anonymous", route, 401)
            return
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        if route == "/api/v1/privacy/export":
            db = self._open_database()
            try:
                export = db.export_personal_data(int(payload.get("limit", 1000)))
            finally:
                db.close()
            self._audit("privacy_export", "success", role, route, 200, records=len(export["events"]))
            self._send_json(200, export)
            return
        if route == "/api/v1/privacy/delete":
            if payload.get("confirm") != "DELETE":
                self._send_json(400, {"error": "confirm must equal DELETE"})
                return
            db = self._open_database()
            try:
                deleted = db.delete_personal_data(reset_aggregates=bool(payload.get("reset_aggregates", False)))
            finally:
                db.close()
            shutil.rmtree(stream_frame_directory(self.project_root), ignore_errors=True)
            records = sum(deleted.values())
            self._audit("privacy_delete", "success", role, route, 200, records=records)
            self._send_json(200, {"deleted": deleted, "aggregate_counts_reset": bool(payload.get("reset_aggregates", False))})
            return
        self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self) -> None:  # noqa: N802
        origin = self.headers.get("Origin", "")
        if not origin or origin not in self.app_config.api.allowed_origins:
            self._send_json(403, {"error": "origin not allowed"})
            return
        self.send_response(204)
        self._send_security_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return

    def version_string(self) -> str:
        return self.server_version

    def _required_role(self, route: str) -> str:
        if route.startswith("/api/v1/video/") or route in {"/api/v1/video", "/api/v1/events", "/api/v1/telemetry/current", "/metrics"}:
            return "operator"
        return "viewer"

    def _authorize(self, required_role: str) -> str | None:
        if not self.app_config.api.require_auth:
            return "admin"
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer "):
            self._send_auth_error()
            return None
        supplied = value.removeprefix("Bearer ").strip()
        role = next(
            (candidate for candidate in ("admin", "operator", "viewer") if hmac.compare_digest(supplied, self.tokens.get(candidate, "\0"))),
            None,
        )
        if role is None or ROLE_LEVEL[role] < ROLE_LEVEL[required_role]:
            self._send_auth_error(forbidden=role is not None)
            return None
        return role

    def _send_auth_error(self, forbidden: bool = False) -> None:
        code = 403 if forbidden else 401
        body = {"error": "insufficient role" if forbidden else "authentication required"}
        self._send_json(code, body, extra_headers={"WWW-Authenticate": 'Bearer realm="visitor-counter"'})

    def _rate_limit_ok(self) -> bool:
        bucket = int(time() // 60)
        key = self.client_address[0]
        with _RATE_LIMIT_LOCK:
            current_bucket, count = _RATE_LIMITS.get(key, (bucket, 0))
            if current_bucket != bucket:
                current_bucket, count = bucket, 0
            count += 1
            _RATE_LIMITS[key] = (current_bucket, count)
            if len(_RATE_LIMITS) > 1024:
                for item in [item for item, value in _RATE_LIMITS.items() if value[0] < bucket - 1]:
                    _RATE_LIMITS.pop(item, None)
            return count <= self.app_config.api.max_requests_per_minute

    def _handle_video(self, route: str, query_string: str) -> bool:
        suffix = route.removeprefix("/api/v1/video/").strip("/")
        if suffix.endswith(".mjpg"):
            camera_id = _safe_camera_id(suffix.removesuffix(".mjpg"))
            if not camera_id:
                self._send_json(400, {"error": "invalid camera id"})
                return True
            try:
                fps = float(parse_qs(query_string).get("fps", ["5"])[0])
            except ValueError:
                fps = 5.0
            self._send_mjpeg(camera_id, max(1.0, min(fps, 8.0)))
            return True
        parts = suffix.split("/")
        if len(parts) != 2:
            return False
        camera_id = _safe_camera_id(parts[0])
        if not camera_id:
            self._send_json(400, {"error": "invalid camera id"})
            return True
        if parts[1] == "snapshot.jpg":
            self._send_snapshot(camera_id)
            return True
        if parts[1] == "meta":
            meta = _stream_meta(camera_id)
            if meta and meta.get("age_seconds", 999) <= 3:
                self._send_json(200, meta)
            else:
                self._send_json(404, {"error": "fresh stream frame not available"})
            return True
        return False

    def _send_snapshot(self, camera_id: str) -> None:
        jpg_path, _ = _stream_paths(camera_id)
        meta = _stream_meta(camera_id)
        if not jpg_path.exists() or not meta or meta.get("age_seconds", 999) > 3:
            self._send_json(404, {"error": "fresh stream frame not available"})
            return
        self._send_bytes(200, jpg_path.read_bytes(), "image/jpeg")

    def _send_mjpeg(self, camera_id: str, fps: float) -> None:
        jpg_path, _ = _stream_paths(camera_id)
        if not jpg_path.exists():
            self._send_json(404, {"error": "stream frame not available"})
            return
        interval = 1.0 / fps
        boundary = "personenzaehler-frame"
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
        self._send_security_headers()
        self.send_header("Connection", "close")
        self.end_headers()
        while True:
            try:
                meta = _stream_meta(camera_id)
                if not meta or meta.get("age_seconds", 999) > 3:
                    return
                body = jpg_path.read_bytes()
                self.wfile.write(f"--{boundary}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
                self.wfile.write(body + b"\r\n")
                self.wfile.flush()
                sleep(interval)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    def _send_json(self, code: int, payload: dict, extra_headers: dict[str, str] | None = None) -> None:
        self._send_bytes(code, json.dumps(payload, sort_keys=True).encode("utf-8"), "application/json", extra_headers)

    def _send_bytes(self, code: int, body: bytes, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if self.tls_enabled:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        origin = self.headers.get("Origin", "")
        if origin and origin in self.app_config.api.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _handle_websocket(self) -> None:
        if self.headers.get("Upgrade", "").lower() != "websocket":
            self._send_json(426, {"error": "websocket upgrade required"})
            return
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send_json(400, {"error": "missing websocket key"})
            return
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.close_connection = True
        self.connection.settimeout(3.0)
        while True:
            try:
                if _client_closed(self.connection):
                    break
                self.wfile.write(_websocket_text_frame(json.dumps(cached_status(self.project_root), separators=(",", ":"), sort_keys=True)))
                self.wfile.flush()
                sleep(1.0)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout, OSError):
                break

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length < 0 or length > 4096:
            raise ValueError("request body too large")
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _open_database(self) -> EventDatabase:
        return _open_configured_database(self.project_root, self.app_config)

    def _audit(self, action: str, outcome: str, role: str, route: str, status: int, **details: int) -> None:
        write_audit_event(
            self.project_root / "logs",
            action=action,
            outcome=outcome,
            role=role,
            details={"method": self.command, "route": route, "status": status, **details},
        )


def _websocket_text_frame(text: str) -> bytes:
    payload = text.encode("utf-8")
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", 0x81, length)
    elif length < 65536:
        header = struct.pack("!BBH", 0x81, 126, length)
    else:
        header = struct.pack("!BBQ", 0x81, 127, length)
    return header + payload


def _client_closed(connection: socket.socket) -> bool:
    readable, _, _ = select.select([connection], [], [], 0)
    if not readable:
        return False
    try:
        data = connection.recv(2, socket.MSG_PEEK)
    except BlockingIOError:
        return False
    except OSError:
        return True
    return data == b""


def _events(project_root: Path, limit: int) -> list[dict]:
    config = load_config(project_root / "config" / "config.yaml")
    path = project_root / config.database.path
    if not path.exists():
        return []
    db = _open_configured_database(project_root, config)
    try:
        rows = db.export_personal_data(limit)["events"]
        return [
            {
                "event_id": None,
                "time": row["timestamp"],
                "camera_id": row["camera_id"],
                "direction": row["direction"],
                "event_type": row["event_type"],
                "counted": row["counted"],
                "uncertain": row["uncertain"],
                "confidence": row["confidence"],
                "description": row["reason"],
            }
            for row in rows
        ]
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-preserving visitor-counter API.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    config = load_config(project_root / "config" / "config.yaml")
    api = config.api
    if not api.enabled:
        raise SystemExit("API is disabled in config/config.yaml")
    host = args.host or api.bind_host
    port = args.port or api.port
    tls_cert = args.tls_cert or _configured_path(project_root, api.tls_certificate)
    tls_key = args.tls_key or _configured_path(project_root, api.tls_private_key)
    loopback = host in {"127.0.0.1", "::1", "localhost"}
    if not loopback and (not api.require_auth or not tls_cert or not tls_key):
        raise SystemExit("Non-loopback binding requires authentication plus a TLS certificate and private key.")

    tokens: dict[str, str] = {}
    if api.require_auth:
        for role, variable in {
            "viewer": api.viewer_token_env,
            "operator": api.operator_token_env,
            "admin": api.admin_token_env,
        }.items():
            token = os.environ.get(variable, "")
            if len(token) < api.minimum_token_length:
                raise SystemExit(f"Missing or too-short {role} token in environment variable {variable}.")
            tokens[role] = token
        if len(set(tokens.values())) != len(tokens):
            raise SystemExit("Viewer, operator, and admin tokens must be different.")

    StatusHandler.project_root = project_root
    StatusHandler.app_config = config
    StatusHandler.tokens = tokens
    StatusHandler.tls_enabled = bool(tls_cert and tls_key)
    server = ThreadingHTTPServer((host, port), StatusHandler)
    server.daemon_threads = True
    if tls_cert and tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        context.load_cert_chain(str(tls_cert), str(tls_key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
    scheme = "https" if StatusHandler.tls_enabled else "http"
    write_audit_event(
        project_root / "logs",
        action="api_start",
        outcome="success",
        role="system",
        details={"tls": StatusHandler.tls_enabled, "status": 0},
    )
    print(f"status API listening on {scheme}://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


def _configured_path(project_root: Path, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (project_root / path).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
