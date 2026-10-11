#!/usr/bin/env python3
"""Fail-closed release gates for unattended Raspberry Pi deployments."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

CI_URL = ("https://api.github.com/repos/1234Taschenlampe/"
          "PersonenZ-hler/commits/{sha}/check-runs?per_page=100")
REQUIRED_CHECKS = frozenset(("test (3.11)", "test (3.12)", "package"))


def ci_approved(sha: str) -> tuple[bool, str]:
    """Require CI success from GitHub Actions for this exact commit, not main."""
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha.lower()):
        return False, "Ungueltige Revision"
    request = urllib.request.Request(
        CI_URL.format(sha=sha),
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "Personenzaehler-Safe-Updater/2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
        jobs = result.get("check_runs")
        if not isinstance(jobs, list):
            return False, "Ungueltige CI-Antwort"
        successful = {
            job.get("name")
            for job in jobs if isinstance(job, dict)
            and job.get("status") == "completed"
            and job.get("conclusion") == "success"
            and isinstance(job.get("app"), dict)
            and job["app"].get("slug") == "github-actions"
        }
        missing = REQUIRED_CHECKS - successful
        if missing:
            return False, "CI fehlt oder ist fehlgeschlagen: " + ", ".join(sorted(missing))
        return True, "Erforderliche CI-Jobs erfolgreich"
    except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
        return False, "GitHub-CI nicht pruefbar: " + type(exc).__name__


def _run(args: list[str], root: Path, *, timeout: int = 90, env=None) -> str:
    result = subprocess.run(
        args, cwd=root, env=env, timeout=timeout, check=True, text=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def preflight_candidate(root: Path, state_dir: Path, sha: str) -> None:
    """Run syntax/import checks on an isolated Git worktree BEFORE deployment."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=state_dir) as dirname:
        candidate = Path(dirname) / "source"
        _run(["git", "-C", str(root), "worktree", "add", "--detach",
              str(candidate), sha], root)
        try:
            for script in ("scripts/install_linux_app.sh",
                           "scripts/install_autostart.sh",
                           "scripts/quick_install.sh"):
                _run(["bash", "-n", str(candidate / script)], candidate)
            _run(["python3", "-m", "compileall", "-q", "src", "scripts"],
                 candidate, timeout=120)
            venv_python = root / ".venv/bin/python"
            if venv_python.is_file():
                _run([str(venv_python), "-c",
                      "import visitor_counter.inference_pipeline, visitor_counter.service"],
                     candidate, timeout=45,
                     env={**os.environ, "PYTHONPATH": str(candidate / "src"),
                          "PERSONENZAEHLER_USE_XDG": "1"})
        finally:
            _run(["git", "-C", str(root), "worktree", "remove", "--force",
                  str(candidate)], root)


def service_paths_correct(
    root: Path, previous: dict[str, bool],
) -> tuple[bool, str]:
    """Never activate code from another checkout than that used by services."""
    for name, was_running in previous.items():
        if not was_running:
            continue
        try:
            configured = _run(["systemctl", "--user", "show", name,
                               "--property=WorkingDirectory", "--value"],
                              root, timeout=10)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False, f"{name}: Arbeitsverzeichnis unbekannt"
        if not configured or Path(configured).expanduser().resolve() != root.resolve():
            return False, f"{name} nutzt eine andere Installation ({configured})"
    return True, "Dienstpfade stimmen"


def status_file() -> Path:
    base = os.environ.get("PERSONENZAEHLER_DATA_DIR")
    if base:
        return Path(base).expanduser() / "live_status.json"
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return data_home / "personenzaehler/live_status.json"


def _read_status() -> dict:
    try:
        payload = json.loads(status_file().read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def healthy_cameras_before_update() -> set[str]:
    """Only monitor cameras that were working directly before deployment."""
    payload = _read_status()
    try:
        if time.time() - float(payload.get("timestamp", 0)) > 45:
            return set()
        if not payload.get("runtime", {}).get("detector_active", False):
            return set()
        return {
            camera["camera_id"]
            for camera in payload.get("cameras", [])
            if camera.get("camera_id")
            and camera.get("ai_processed_frames", 0) > 0
            and camera.get("seconds_since_last_ai_frame") is not None
            and camera["seconds_since_last_ai_frame"] < 30
            and camera.get("inference_status") == "active"
        }
    except (ValueError, TypeError, AttributeError, KeyError):
        return set()


def ai_recovered(camera_ids: set[str], deployed_at: float) -> bool:
    payload = _read_status()
    try:
        timestamp = float(payload.get("timestamp", 0))
        if timestamp < deployed_at or time.time() - timestamp > 15:
            return False
        if not payload.get("runtime", {}).get("detector_active", False):
            return False
        cameras = {
            camera["camera_id"]: camera for camera in payload.get("cameras", [])
            if isinstance(camera, dict) and camera.get("camera_id")
        }
        return all(
            cameras.get(camera_id, {}).get("ai_processed_frames", 0) >= 2
            and cameras[camera_id].get("inference_status") == "active"
            and cameras[camera_id].get("seconds_since_last_ai_frame") is not None
            and cameras[camera_id]["seconds_since_last_ai_frame"] < 15
            for camera_id in camera_ids
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def wait_for_recovery(root: Path, previous: dict[str, bool], camera_ids: set[str],
                      deployed_at: float, is_running, *,
                      attempts: int = 60, delay: float = 2.0) -> None:
    """Do not declare success until old online cameras perform new inferences."""
    required_services = [name for name, active in previous.items() if active]
    for index in range(attempts):
        running = all(is_running(root, unit) for unit in required_services)
        if running and (not camera_ids or ai_recovered(camera_ids, deployed_at)):
            return
        if index + 1 < attempts:
            time.sleep(delay)
    missing = [unit for unit in required_services if not is_running(root, unit)]
    if missing:
        raise RuntimeError("Dienste nach Update ausgefallen: " + ", ".join(missing))
    raise RuntimeError("KI-Verarbeitung nicht wiederhergestellt: " +
                       ", ".join(sorted(camera_ids)))
