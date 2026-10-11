#!/usr/bin/env python3
"""Unattended, fast-forward-only GitHub updates for the source Pi installation.

Only the pinned origin/main is trusted. Data, config, secrets and licence live
outside the Git checkout. Failed updates attempt to restore the previous HEAD.
No hardware changes are made unless the installer explicitly requires them.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import update_safety
from datetime import datetime, timezone

EXPECTED_ORIGIN = "https://github.com/1234Taschenlampe/PersonenZ-hler"
BRANCH = "main"
MANAGED_SERVICES = (
    "personenzaehler.service",
    "personenzaehler-mobile-api.service",
    "visitor-counter.service",
)


def log(message: str) -> None:
    print(f"[PersonenZähler Update] {message}", flush=True)


def allowed_origin(url: str) -> bool:
    # A pinned upstream prevents automatically executing arbitrary fork code.
    return url.strip().removesuffix(".git").rstrip("/") == EXPECTED_ORIGIN


def exec_checked(
    argv: list[str], *, cwd: Path, timeout: int = 120,
    env: dict[str, str] | None = None, capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, env=env, timeout=timeout,
        stdin=subprocess.DEVNULL, text=True, check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def git(root: Path, *args: str, timeout: int = 120) -> str:
    return exec_checked(
        ["git", "-C", str(root), *args], cwd=root,
        timeout=timeout, capture=True,
    ).stdout.strip()


def is_clean(root: Path) -> bool:
    return not git(root, "status", "--porcelain", "--untracked-files=no")


def service_running(root: Path, unit: str) -> bool:
    try:
        exec_checked(["systemctl", "--user", "is-active", "--quiet", unit], cwd=root, timeout=10)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def write_result(state_dir: Path, **values: object) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    state_dir.chmod(0o700)
    destination = state_dir / "auto-update-status.json"
    temp = destination.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(), **values}, sort_keys=True),
        encoding="utf-8",
    )
    temp.chmod(0o600)
    temp.replace(destination)


def check_health(root: Path, previously_running: dict[str, bool]) -> None:
    # A previously stopped service must not be started without user consent.
    running = [name for name, enabled in previously_running.items() if enabled]
    for attempt in range(10):
        if all(service_running(root, unit) for unit in running):
            return
        if attempt != 9:
            time.sleep(2)
    missing = [name for name in running if not service_running(root, name)]
    raise RuntimeError("Updated service did not recover: " + ", ".join(missing))


def installer(root: Path, *, rollback: bool = False) -> None:
    # Sudo must never display a password prompt in a scheduled unit. Missing
    # privileged dependencies require a manual installation.
    env = dict(os.environ)
    env.update({
        "PERSONENZAEHLER_USE_XDG": "1",
        "PERSONENZAEHLER_CODE_UPDATED": "1",
        "DEBIAN_FRONTEND": "noninteractive",
        "GIT_TERMINAL_PROMPT": "0",
        "PERSONENZAEHLER_UNATTENDED": "1",
    })
    args = ["bash", str(root / "scripts" / "install_linux_app.sh")]
    # Revalidate existing models even for rollback: --skip-models deliberately
    # exits with partial-install status and would misreport a healthy restore.
    if rollback:
        log("Vorherige Version und bestehende Modelle wiederherstellen.")
    exec_checked(args, cwd=root, env=env, timeout=1200)


def update(root: Path, *, check_only: bool = False) -> int:
    root = root.expanduser().resolve()
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "personenzaehler"
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "personenzaehler"
    state_dir = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "personenzaehler"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.chmod(0o700)
    if (config_dir / "auto-update.paused").exists():
        log("Automatische Updates pausiert: auto-update.paused")
        write_result(state_dir, result="paused")
        return 0
    if not (root / ".git").is_dir():
        log(f"Kein Git-Checkout: {root}; keine Änderungen.")
        return 2

    # Shared with quick_install.sh: neither operation can mutate the checkout
    # while the other updates dependencies or user services.
    with (cache_dir / "quick-install.lock").open("a+") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Installer läuft bereits; Versuch auf nächsten Timer verschoben.")
            return 0

        try:
            branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
            origin = git(root, "remote", "get-url", "origin")
            if branch != BRANCH or not allowed_origin(origin):
                raise RuntimeError("Nur der freigegebene GitHub-origin/main-Checkout wird automatisch aktualisiert.")
            if not is_clean(root):
                raise RuntimeError("Lokale Änderungen im Quellcode: automatisches Update verweigert.")

            before = git(root, "rev-parse", "HEAD")
            exec_checked(
                ["git", "-C", str(root), "fetch", "--quiet", "--no-tags", "origin", "refs/heads/main"],
                cwd=root, timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            after = git(root, "rev-parse", "FETCH_HEAD")
            if before == after:
                log(f"Bereits aktuell: {before[:12]}")
                write_result(state_dir, result="up_to_date", revision=before)
                return 0

            try:
                exec_checked(
                    ["git", "-C", str(root), "merge-base", "--is-ancestor", before, after],
                    cwd=root, timeout=15, capture=True,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError("Git-Historie nicht Fast-Forward; kein automatisches Update.") from exc

            log(f"Update gefunden: {before[:12]} -> {after[:12]}")
            if check_only:
                write_result(state_dir, result="available", revision=before, available_revision=after)
                return 0

            # Fail closed: never deploy a commit that lacks passing CI.
            approved, explanation = update_safety.ci_approved(after)
            if not approved:
                log("Update wartet auf erfolgreiche GitHub-Tests: " + explanation)
                write_result(state_dir, result="blocked_ci", revision=before,
                             available_revision=after, error=explanation)
                return 0

            # Tests run on an isolated candidate checkout; production stays
            # online and untouched if code/shell syntax or imports are invalid.
            update_safety.preflight_candidate(root, state_dir, after)
            previously_running = {unit: service_running(root, unit) for unit in MANAGED_SERVICES}
            correct, explanation = update_safety.service_paths_correct(root, previously_running)
            if not correct:
                raise RuntimeError(explanation)
            working_cameras = (
                update_safety.healthy_cameras_before_update()
                if previously_running.get("personenzaehler.service") else set()
            )
            exec_checked(
                ["git", "-C", str(root), "merge", "--ff-only", after], cwd=root, timeout=90,
            )
            installed_at = time.time()
            try:
                installer(root)
                update_safety.wait_for_recovery(
                    root, previously_running, working_cameras,
                    installed_at, service_running,
                )
            except Exception as exc:
                log(f"Update fehlgeschlagen ({type(exc).__name__}): {exc}; Rollback starten.")
                rollback_error: Exception | None = None
                try:
                    if git(root, "rev-parse", "HEAD") != after or not is_clean(root):
                        raise RuntimeError("Git-Checkout nach Fehler verändert; kein destruktiver Rollback.")
                    # Safe only because the tracked worktree was clean before
                    # upgrading and is still unchanged by the installer.
                    exec_checked(
                        ["git", "-C", str(root), "reset", "--hard", before], cwd=root, timeout=90,
                    )
                    installer(root, rollback=True)
                    update_safety.wait_for_recovery(
                        root, previously_running, set(), time.time(), service_running,
                        attempts=30,
                    )
                except Exception as restore_exc:
                    rollback_error = restore_exc
                    log(f"Rollback NICHT vollständig: {restore_exc}")
                write_result(
                    state_dir, result="failed" if rollback_error else "rolled_back",
                    revision=before, attempted_revision=after,
                    error=str(exc), rollback_error=str(rollback_error) if rollback_error else None,
                )
                return 1

            log(f"Update installiert und laufende Dienste geprüft: {after[:12]}")
            write_result(state_dir, result="updated", previous_revision=before, revision=after)
            return 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, RuntimeError) as exc:
            log(f"Prüfung abgebrochen: {type(exc).__name__}: {exc}")
            write_result(state_dir, result="error", error=str(exc))
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Periodischer GitHub-Updater für PersonenZähler")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check-only", action="store_true", help="Neue Version suchen, aber nichts installieren")
    args = parser.parse_args()
    return update(args.project_root, check_only=args.check_only)


if __name__ == "__main__":
    sys.exit(main())
