from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _set_private(path)


def require_privacy_approval(path: Path) -> dict[str, Any]:
    """Fail closed unless a time-limited, operator-owned training approval exists."""
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read privacy approval: {path}") from exc
    required = ("approved", "purpose", "legal_basis", "controller", "expires_at")
    if not isinstance(approval, dict) or any(not approval.get(key) for key in required):
        raise RuntimeError(f"Privacy approval must contain: {', '.join(required)}")
    if approval["approved"] is not True:
        raise RuntimeError("Training data processing has not been approved.")
    expires = datetime.fromisoformat(str(approval["expires_at"]).replace("Z", "+00:00"))
    if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
        raise RuntimeError("Training privacy approval has expired.")
    return approval


def secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _set_private(path, 0o700)


def secure_file(path: Path) -> None:
    _set_private(path, 0o600)


def _set_private(path: Path, mode: int = 0o600) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def run_command(command: list[str], timeout: int | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except Exception as exc:  # noqa: BLE001
        return {"command": command, "error": str(exc)}
