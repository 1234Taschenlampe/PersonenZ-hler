from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from threading import Lock
from time import time
from typing import Mapping


_AUDIT_LOCK = Lock()
_SENSITIVE_PATTERNS = (
    (re.compile(r"\bbbox\s*=\s*(?:\([^)]*\)|\[[^]]*\]|\S+)", re.IGNORECASE), "bbox=[redacted]"),
    (re.compile(r"\b(center|previous_center|anchor)\s*=\s*(?:\([^)]*\)|\[[^]]*\]|\S+)", re.IGNORECASE), r"\1=[redacted]"),
    (re.compile(r"\b(track_id|global_person_id|local_track_id|session_id|passage_id)\s*=\s*[^ ,]+", re.IGNORECASE), r"\1=[redacted]"),
    (re.compile(r"\b(entered_ids|exited_ids)\s*=\s*\[[^]]*]", re.IGNORECASE), r"\1=[redacted]"),
    (re.compile(r"\bframe(_id)?\s*=\s*\d+", re.IGNORECASE), "frame=[redacted]"),
    (re.compile(r"\b(authorization|bearer|password|secret|token|api[_-]?key)\b\s*[:=]\s*\S+", re.IGNORECASE), r"\1=[redacted]"),
)


class SensitiveDataFilter(logging.Filter):
    """Last-line defense against identifiers or image-derived coordinates in logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in _SENSITIVE_PATTERNS:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(log_dir: Path, retention_days: int = 7) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    _set_mode(log_dir, 0o700)
    _delete_expired_logs(log_dir, retention_days)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    privacy_filter = SensitiveDataFilter()
    app_handler = RotatingFileHandler(log_dir / "application.log", maxBytes=2_000_000, backupCount=3)
    app_handler.setFormatter(formatter)
    app_handler.setLevel(logging.INFO)
    app_handler.addFilter(privacy_filter)

    error_handler = RotatingFileHandler(log_dir / "errors.log", maxBytes=1_000_000, backupCount=3)
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(privacy_filter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)
    stream_handler.addFilter(privacy_filter)

    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(stream_handler)
    for path in (log_dir / "application.log", log_dir / "errors.log"):
        _set_mode(path, 0o600)


def write_audit_event(
    log_dir: Path,
    *,
    action: str,
    outcome: str,
    role: str = "anonymous",
    details: Mapping[str, str | int | float | bool | None] | None = None,
) -> None:
    """Append an allowlisted security audit record without IPs, tokens, paths, or payloads."""
    allowed_details = {
        key: value
        for key, value in (details or {}).items()
        if key in {"method", "route", "status", "records", "tls", "request_id"}
        and isinstance(value, (str, int, float, bool, type(None)))
    }
    record = {
        "timestamp": time(),
        "action": action[:80],
        "outcome": outcome[:40],
        "role": role if role in {"anonymous", "viewer", "operator", "admin", "system"} else "unknown",
        "details": allowed_details,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    _set_mode(log_dir, 0o700)
    path = log_dir / "audit.jsonl"
    with _AUDIT_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n")
        _set_mode(path, 0o600)


def _delete_expired_logs(log_dir: Path, retention_days: int) -> None:
    cutoff = time() - max(1, retention_days) * 86_400
    for path in log_dir.glob("*.log*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass
    audit_path = log_dir / "audit.jsonl"
    try:
        if audit_path.is_file() and audit_path.stat().st_mtime < cutoff:
            audit_path.unlink()
    except OSError:
        pass


def _set_mode(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass
