from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any

from .configuration import AppConfig, load_config, privacy_readiness_errors
from .data_protection import load_data_protector
from .database import EventDatabase
from .license_service import LicenseService, LicenseStatus
from .runtime_paths import RuntimePaths
from .service_manager import ServiceManager, ServiceStatus


@dataclass(frozen=True)
class DashboardSnapshot:
    timestamp: float
    counts: dict[str, Any] = field(default_factory=dict)
    cameras: list[dict[str, Any]] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    api: dict[str, Any] = field(default_factory=dict)
    database: dict[str, Any] = field(default_factory=dict)
    service: ServiceStatus | None = None
    license: LicenseStatus | None = None
    privacy_errors: tuple[str, ...] = ()


class ApplicationService:
    """Read-mostly facade shared by desktop pages and the first-run wizard."""

    def __init__(
        self, paths: RuntimePaths, service_manager: ServiceManager | None = None
    ) -> None:
        self.paths = paths
        self.settings_path = paths.config_file
        self.service_manager = service_manager or ServiceManager(
            "personenzaehler.service", user_service=not paths.system_layout
        )
        self.license_service = LicenseService(paths)

    def config(self) -> AppConfig:
        return load_config(self.settings_path)

    def snapshot(self) -> DashboardSnapshot:
        config = self.config()
        live = self._read_live_status()
        counts = dict(live.get("counts", {})) if live else self._database_counts(config)
        counts.setdefault("inside", 0)
        counts.setdefault("entered", 0)
        counts.setdefault("exited", 0)
        counts.setdefault(
            "throughput",
            int(counts.get("entered") or 0) + int(counts.get("exited") or 0),
        )
        counts.setdefault("daily_unique", self._daily_unique_count())
        counts.setdefault("suppressed", 0)
        counts.setdefault("uncertain", 0)
        counts.setdefault("wrong_way", 0)
        cameras = (
            list(live.get("cameras", []))
            if live
            else [
                {
                    "camera_id": item.camera_id,
                    "name": item.display_name,
                    "role": item.role,
                    "source": item.device or "nicht konfiguriert",
                    "status": "unbekannt",
                    "fps": None,
                    "width": item.width,
                    "height": item.height,
                }
                for item in config.cameras.values()
            ]
        )
        database_path = self._database_path(config)
        return DashboardSnapshot(
            timestamp=time(),
            counts=counts,
            cameras=cameras,
            runtime=dict(live.get("runtime", {})) if live else {},
            api={
                "enabled": config.api.enabled,
                "bind_host": config.api.bind_host,
                "port": config.api.port,
                "tls": bool(config.api.tls_certificate and config.api.tls_private_key),
            },
            database={
                "path": str(database_path),
                "exists": database_path.exists(),
                "size_bytes": database_path.stat().st_size
                if database_path.exists()
                else 0,
            },
            service=self.service_manager.status(),
            license=self.license_service.inspect(),
            privacy_errors=tuple(privacy_readiness_errors(config)),
        )

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        config = self.config()
        path = self._database_path(config)
        if not path.exists():
            return []
        db = EventDatabase(
            path,
            store_personal_events=config.database.store_events,
            retention_hours=config.database.retention_hours,
            protector=load_data_protector(config.database, self.paths.project_root),
            require_encryption=config.database.encryption_required,
        )
        try:
            payload = db.export_personal_data(max(1, min(limit, 500)))
            return list(payload.get("events", []))
        except (RuntimeError, sqlite3.Error, ValueError):
            return []
        finally:
            db.close()

    def hourly_history(self, hours: int = 24) -> list[dict[str, Any]]:
        path = self._database_path(self.config())
        result = [
            {"hour": index, "entries": 0, "exits": 0}
            for index in range(max(1, min(hours, 48)))
        ]
        if not path.exists():
            return result
        cutoff = time() - len(result) * 3600
        try:
            connection = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2
            )
            rows = connection.execute(
                "SELECT timestamp, direction, COUNT(*) FROM counting_events "
                "WHERE timestamp >= ? AND counted = 1 AND uncertain = 0 GROUP BY CAST(timestamp / 3600 AS INTEGER), direction",
                (cutoff,),
            ).fetchall()
            connection.close()
        except sqlite3.Error:
            return result
        first = int(cutoff // 3600)
        for timestamp, direction, count in rows:
            index = int(float(timestamp) // 3600) - first
            if 0 <= index < len(result):
                key = "entries" if direction == "IN" else "exits"
                result[index][key] += int(count)
        return result

    def delete_personal_data(self, reset_aggregates: bool = False) -> dict[str, int]:
        config = self.config()
        path = self._database_path(config)
        db = EventDatabase(
            path,
            store_personal_events=config.database.store_events,
            retention_hours=config.database.retention_hours,
            protector=load_data_protector(config.database, self.paths.project_root),
            require_encryption=config.database.encryption_required,
        )
        try:
            return db.delete_personal_data(reset_aggregates=reset_aggregates)
        finally:
            db.close()

    def mark_first_run_complete(self) -> None:
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "completed_at": datetime.now().astimezone().isoformat(),
            "version": 1,
        }
        self.paths.first_run_marker.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _read_live_status(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(
                self.paths.live_status_file.read_text(encoding="utf-8")
            )
            if time() - float(payload.get("timestamp", 0)) > 15:
                return None
            return payload if isinstance(payload, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    def _database_path(self, config: AppConfig) -> Path:
        path = Path(config.database.path).expanduser()
        if path.is_absolute():
            return path
        if self.paths.system_layout:
            return self.paths.data_dir / path.name
        return self.paths.project_root / path

    def _database_counts(self, config: AppConfig) -> dict[str, Any]:
        path = self._database_path(config)
        if not path.exists():
            return {}
        try:
            connection = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2
            )
            row = connection.execute(
                "SELECT entered, exited, inside, wrong_way FROM global_counts WHERE id=1"
            ).fetchone()
            suppressed = connection.execute(
                "SELECT COUNT(*) FROM counting_events WHERE counted=0"
            ).fetchone()[0]
            uncertain = connection.execute(
                "SELECT COUNT(*) FROM counting_events WHERE uncertain=1"
            ).fetchone()[0]
            connection.close()
        except sqlite3.Error:
            return {}
        if row is None:
            return {}
        return {
            "entered": int(row[0]),
            "exited": int(row[1]),
            "inside": int(row[2]),
            "wrong_way": int(row[3]),
            "suppressed": int(suppressed),
            "uncertain": int(uncertain),
        }

    def _daily_unique_count(self) -> int:
        path = self.paths.data_dir / "daily_unique.sqlite3"
        if not path.exists():
            return 0
        day = datetime.now().astimezone().date().isoformat()
        try:
            connection = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2
            )
            row = connection.execute(
                "SELECT COUNT(*) FROM daily_unique_profiles WHERE day=?", (day,)
            ).fetchone()
            connection.close()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0
