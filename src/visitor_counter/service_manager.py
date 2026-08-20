from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, ClassVar


class ServiceState(str, Enum):
    RUNNING = "läuft"
    STOPPED = "gestoppt"
    STARTING = "startet"
    FAILED = "Fehler"
    UNAVAILABLE = "nicht verfügbar"


@dataclass(frozen=True)
class ServiceStatus:
    state: ServiceState
    detail: str = ""
    active_state: str = "unknown"
    sub_state: str = "unknown"


class ServiceActionError(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess[str]]


class ServiceManager:
    """Safe systemd adapter used by the GUI and diagnostics."""

    _ACTIONS: ClassVar[set[str]] = {"start", "stop", "restart"}

    def __init__(
        self,
        unit: str = "personenzaehler.service",
        *,
        user_service: bool = False,
        runner: Runner = subprocess.run,
        admin_helper: Path = Path("/usr/lib/personenzaehler/personenzaehler-admin"),
    ) -> None:
        self.unit = unit
        self.user_service = user_service
        self.runner = runner
        self.admin_helper = admin_helper

    def _systemctl(self, *arguments: str) -> list[str]:
        command = ["systemctl"]
        if self.user_service:
            command.append("--user")
        return [*command, *arguments]

    def status(self) -> ServiceStatus:
        if os.name != "posix" or shutil.which("systemctl") is None:
            return ServiceStatus(
                ServiceState.UNAVAILABLE,
                "systemd ist auf diesem System nicht verfügbar",
            )
        try:
            result = self.runner(
                self._systemctl(
                    "show", self.unit, "--property=ActiveState,SubState", "--value"
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ServiceStatus(ServiceState.UNAVAILABLE, str(exc))
        values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        active = values[0] if values else "unknown"
        sub = values[1] if len(values) > 1 else "unknown"
        state = {
            "active": ServiceState.RUNNING,
            "activating": ServiceState.STARTING,
            "failed": ServiceState.FAILED,
            "inactive": ServiceState.STOPPED,
            "deactivating": ServiceState.STOPPED,
        }.get(active, ServiceState.UNAVAILABLE)
        detail = result.stderr.strip() if result.returncode else ""
        return ServiceStatus(state, detail, active, sub)

    def action(self, action: str) -> ServiceStatus:
        if action not in self._ACTIONS:
            raise ServiceActionError(f"Nicht erlaubte Dienstaktion: {action}")
        if os.name != "posix" or shutil.which("systemctl") is None:
            raise ServiceActionError("systemd ist auf diesem System nicht verfügbar")
        if self.user_service:
            command = self._systemctl(action, self.unit)
        else:
            if shutil.which("pkexec") is None or not self.admin_helper.exists():
                raise ServiceActionError(
                    "Die grafische Systemberechtigung ist nicht installiert"
                )
            command = ["pkexec", str(self.admin_helper), "service", action, self.unit]
        try:
            result = self.runner(
                command, check=False, capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ServiceActionError(f"Dienstaktion fehlgeschlagen: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise ServiceActionError(
                detail or f"Dienstaktion endete mit Status {result.returncode}"
            )
        return self.status()

    def recent_logs(self, lines: int = 200) -> str:
        if os.name != "posix" or shutil.which("journalctl") is None:
            return "systemd-Journal ist auf diesem System nicht verfügbar."
        command = ["journalctl"]
        if self.user_service:
            command.append("--user")
        command.extend(
            [
                "-u",
                self.unit,
                "-n",
                str(max(1, min(lines, 1000))),
                "--no-pager",
                "--output=short-iso",
            ]
        )
        try:
            result = self.runner(
                command, check=False, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"Logs konnten nicht gelesen werden: {exc}"
        return (
            result.stdout
            if result.returncode == 0
            else (result.stderr or result.stdout)
        )
