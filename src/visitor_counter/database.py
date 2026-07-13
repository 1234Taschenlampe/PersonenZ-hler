from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import sqlite3
import threading
from time import time

from .data_protection import DataProtector
from .types import ConsensusDecision, Direction

LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class TimeoutResult:
    closed_sessions: int
    last_timeout_at: float | None


class EventDatabase:
    def __init__(
        self,
        path: Path,
        *,
        store_personal_events: bool = True,
        retention_hours: int = 24,
        protector: DataProtector | None = None,
        require_encryption: bool = False,
    ) -> None:
        self.path = path
        self.store_personal_events = store_personal_events
        self.retention_hours = retention_hours
        self.protector = protector
        if store_personal_events and require_encryption and protector is None:
            raise RuntimeError("Personal event storage requires the configured data encryption key.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise RuntimeError(f"Refusing a symlinked database path: {self.path}")
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA secure_delete=ON")
        self._connection.execute("PRAGMA trusted_schema=OFF")
        self._migrate()
        if not self.store_personal_events:
            self.delete_personal_data(reset_aggregates=False)
        elif self.protector is not None:
            self._protect_existing_rows()
        self.purge_expired()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _run_transaction(self, func, *args, **kwargs):
        in_tx = self._connection.in_transaction
        if not in_tx:
            self._connection.execute("BEGIN IMMEDIATE")
        try:
            result = func(*args, **kwargs)
            if not in_tx:
                self._connection.execute("COMMIT")
            return result
        except Exception as e:
            if not in_tx:
                try:
                    self._connection.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
            raise e

    def _migrate(self) -> None:
        cursor = self._connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        schema_version = 0
        if "presence_sessions" in tables:
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(presence_sessions)").fetchall()}
            if "id" in columns and "session_id" not in columns:
                schema_version = 1
        
        if schema_version == 0 and "app_settings" in tables:
            try:
                row = self._connection.execute("SELECT value FROM app_settings WHERE key = 'schema_version'").fetchone()
                if row:
                    schema_version = int(row[0])
            except sqlite3.OperationalError:
                pass

        # Never create an unencrypted copy of legacy personal data.
        if self.path.exists() and schema_version == 1:
            if self.protector is None:
                raise RuntimeError("A data encryption key is required to migrate the legacy personal-event database.")
            backup_path = self.path.parent / f"{self.path.name}.backup_{int(time())}.fernet"
            backup_path.write_bytes(self.protector.encrypt_bytes(self.path.read_bytes()))
            try:
                backup_path.chmod(0o600)
            except OSError:
                pass
            LOGGER.info("DATABASE_MIGRATION_BACKUP_CREATED encrypted=true")

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS counting_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    camera_id TEXT NOT NULL,
                    local_track_id INTEGER NOT NULL,
                    global_person_id INTEGER,
                    session_id INTEGER,
                    passage_id TEXT,
                    direction TEXT NOT NULL,
                    event_type TEXT NOT NULL DEFAULT 'crossing',
                    counted INTEGER NOT NULL,
                    uncertain INTEGER NOT NULL,
                    consensus_reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    model_name TEXT NOT NULL,
                    processing_ms REAL,
                    created_at REAL NOT NULL DEFAULT (unixepoch())
                )
                """
            )
            self._add_column("counting_events", "global_person_id", "INTEGER")
            self._add_column("counting_events", "session_id", "INTEGER")
            self._add_column("counting_events", "passage_id", "TEXT")
            self._add_column("counting_events", "event_type", "TEXT NOT NULL DEFAULT 'crossing'")
            self._add_column("counting_events", "created_at", "REAL NOT NULL DEFAULT 0")

            if schema_version == 1:
                self._connection.execute("ALTER TABLE presence_sessions RENAME TO _presence_sessions_old")
                self._connection.execute(
                    """
                    CREATE TABLE presence_sessions (
                        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        global_person_id INTEGER NOT NULL,
                        entry_time REAL,
                        last_seen_time REAL,
                        exit_time REAL,
                        status TEXT NOT NULL,
                        entry_camera TEXT,
                        exit_camera TEXT,
                        entry_event_id INTEGER,
                        exit_event_id INTEGER,
                        exit_reason TEXT,
                        confidence REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                self._connection.execute(
                    """
                    INSERT INTO presence_sessions (
                        session_id, global_person_id, entry_time, last_seen_time, exit_time, status,
                        entry_camera, exit_camera, entry_event_id, exit_event_id, exit_reason, confidence, created_at, updated_at
                    )
                    SELECT
                        id, global_person_id, started_at, last_seen_at, ended_at, status,
                        involved_cameras, NULL, entry_event_id, exit_event_id, close_reason, confidence, created_at, updated_at
                    FROM _presence_sessions_old
                    """
                )
                self._connection.execute("DROP TABLE _presence_sessions_old")
            else:
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS presence_sessions (
                        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        global_person_id INTEGER NOT NULL,
                        entry_time REAL,
                        last_seen_time REAL,
                        exit_time REAL,
                        status TEXT NOT NULL,
                        entry_camera TEXT,
                        exit_camera TEXT,
                        entry_event_id INTEGER,
                        exit_event_id INTEGER,
                        exit_reason TEXT,
                        confidence REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )

            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS global_persons (
                    global_person_id INTEGER PRIMARY KEY,
                    first_seen_time REAL NOT NULL,
                    last_seen_time REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_status (
                    camera_id TEXT PRIMARY KEY,
                    connected INTEGER NOT NULL,
                    fps REAL NOT NULL,
                    last_seen_time REAL,
                    last_error TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS timeout_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL UNIQUE,
                    global_person_id INTEGER NOT NULL,
                    timeout_at REAL NOT NULL,
                    timeout_minutes INTEGER NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    severity TEXT NOT NULL,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    global_person_id INTEGER,
                    session_id INTEGER,
                    payload TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS global_counts (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    entered INTEGER NOT NULL DEFAULT 0,
                    exited INTEGER NOT NULL DEFAULT 0,
                    inside INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO global_counts (id, entered, exited, inside) VALUES (1, 0, 0, 0)"
            )
            
            row_cnt = self._connection.execute("SELECT entered, exited, inside FROM global_counts WHERE id = 1").fetchone()
            if row_cnt == (0, 0, 0):
                inside_cnt = self._connection.execute("SELECT COUNT(*) FROM presence_sessions WHERE status = 'inside'").fetchone()[0]
                entered_cnt = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE counted = 1 AND uncertain = 0 AND direction = 'in'").fetchone()[0]
                exited_cnt = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE counted = 1 AND uncertain = 0 AND direction = 'out'").fetchone()[0]
                self._connection.execute(
                    "UPDATE global_counts SET entered = ?, exited = ?, inside = ? WHERE id = 1",
                    (entered_cnt, exited_cnt, inside_cnt)
                )

            self._connection.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('schema_version', '2', ?)",
                (time(),)
            )

            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_open ON presence_sessions(global_person_id, status)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_status_seen ON presence_sessions(status, last_seen_time)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_global ON counting_events(global_person_id, timestamp)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_counted_direction ON counting_events(counted, uncertain, direction)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_global_persons_last_seen ON global_persons(last_seen_time)")
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_counting_events_person_passage_type
                ON counting_events(global_person_id, passage_id, event_type)
                WHERE global_person_id IS NOT NULL AND passage_id IS NOT NULL
                """
            )
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_presence_sessions_entry_event
                ON presence_sessions(entry_event_id)
                WHERE entry_event_id IS NOT NULL
                """
            )
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_presence_sessions_exit_event
                ON presence_sessions(exit_event_id)
                WHERE exit_event_id IS NOT NULL
                """
            )

            self._connection.execute("COMMIT")
        except Exception as e:
            try:
                self._connection.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise e

    def _add_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row[1] for row in self._connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def record_decision(self, decision: ConsensusDecision, model_name: str, processing_ms: float | None = None) -> int:
        if not self.store_personal_events:
            return 0
        with self._lock:
            return self._run_transaction(self._record_decision_tx, decision, model_name, processing_ms)

    def _record_decision_tx(self, decision: ConsensusDecision, model_name: str, processing_ms: float | None = None) -> int:
        event = decision.event
        stored_global_id = self._protected_id("person", event.global_person_id)
        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO counting_events (
                timestamp, camera_id, local_track_id, global_person_id, session_id, passage_id,
                direction, event_type, counted, uncertain, consensus_reason, confidence, model_name, processing_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.timestamp,
                self._protected_text(event.camera_id),
                self._protected_id("track", event.local_track_id),
                stored_global_id,
                event.session_id,
                self._protected_pseudonym("passage", event.passage_id),
                event.direction.value,
                "uncertain" if decision.uncertain else "crossing",
                int(decision.counted),
                int(decision.uncertain),
                self._protected_text(decision.reason),
                event.confidence,
                self._protected_text(model_name),
                processing_ms,
                time(),
            ),
        )
        if cursor.rowcount == 0:
            self._record_diagnostic_tx(
                "info", "duplicate_passage_event", "Duplicate passage event suppressed", stored_global_id, event.session_id
            )
            return 0
        event_id = int(cursor.lastrowid)
        self._upsert_person(stored_global_id, event.timestamp)
        if decision.counted and not decision.uncertain and stored_global_id is not None:
            if event.direction == Direction.IN:
                if self._open_session(stored_global_id, event.timestamp, event.camera_id, event_id, event.confidence):
                    self._connection.execute(
                        "UPDATE global_counts SET entered = entered + 1, inside = inside + 1 WHERE id = 1"
                    )
                else:
                    self._connection.execute("UPDATE counting_events SET counted = 0, event_type = 'duplicate_entry' WHERE id = ?", (event_id,))
            elif event.direction == Direction.OUT:
                if self._close_session(stored_global_id, event.timestamp, event.camera_id, event_id, "camera_exit"):
                    self._connection.execute(
                        "UPDATE global_counts SET exited = exited + 1, inside = CASE WHEN inside > 0 THEN inside - 1 ELSE 0 END WHERE id = 1"
                    )
                else:
                    self._connection.execute("UPDATE counting_events SET counted = 0, event_type = 'orphan_exit' WHERE id = ?", (event_id,))
        elif decision.uncertain:
            self._record_diagnostic_tx("warning", "uncertain_event", decision.reason, stored_global_id, event.session_id)
        return event_id

    def record_diagnostic(self, severity: str, code: str, message: str, global_person_id: int | None = None, session_id: int | None = None) -> None:
        if not self.store_personal_events:
            return
        with self._lock:
            stored_global_id = self._protected_id("person", global_person_id)
            self._run_transaction(self._record_diagnostic_tx, severity, code, message, stored_global_id, session_id)

    def _record_diagnostic_tx(self, severity: str, code: str, message: str, global_person_id: int | None = None, session_id: int | None = None) -> None:
        self._connection.execute(
            """
            INSERT INTO diagnostic_events(timestamp, severity, code, message, global_person_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (time(), severity, code, self._protected_text(message), global_person_id, session_id),
        )

    def restore_counts(self) -> dict[str, int]:
        with self._lock:
            row = self._connection.execute("SELECT entered, exited, inside FROM global_counts WHERE id = 1").fetchone()
            if not row:
                self._connection.execute("INSERT OR IGNORE INTO global_counts (id, entered, exited, inside) VALUES (1, 0, 0, 0)")
                row = (0, 0, 0)
            entered, exited, inside = row
            timeouts = self._connection.execute("SELECT COUNT(*) FROM timeout_events").fetchone()
            uncertain = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE uncertain = 1").fetchone()
            suppressed = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE counted = 0").fetchone()
            return {
                "inside": inside,
                "entered": entered,
                "exited": exited,
                "timeouts": int(timeouts[0]),
                "uncertain": int(uncertain[0]),
                "suppressed": int(suppressed[0]),
            }

    def reset_global_counts(self) -> None:
        with self._lock:
            self._run_transaction(self._reset_global_counts_tx)

    def _reset_global_counts_tx(self) -> None:
        self._connection.execute("UPDATE global_counts SET entered = 0, exited = 0, inside = 0 WHERE id = 1")
        self._connection.execute("DELETE FROM presence_sessions")
        self._connection.execute("DELETE FROM counting_events")
        self._connection.execute("DELETE FROM timeout_events")

    def set_global_counts(self, entered: int, exited: int, inside: int) -> None:
        with self._lock:
            self._run_transaction(self._set_global_counts_tx, entered, exited, inside)

    def _set_global_counts_tx(self, entered: int, exited: int, inside: int) -> None:
        self._connection.execute(
            """
            INSERT INTO global_counts(id, entered, exited, inside)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                entered = excluded.entered,
                exited = excluded.exited,
                inside = excluded.inside
            """,
            (max(0, int(entered)), max(0, int(exited)), max(0, int(inside))),
        )

    def update_last_seen(self, global_person_ids: set[int], timestamp: float) -> None:
        if not self.store_personal_events:
            return
        with self._lock:
            protected = {value for value in (self._protected_id("person", item) for item in global_person_ids) if value is not None}
            self._run_transaction(self._update_last_seen_tx, protected, timestamp)

    def _update_last_seen_tx(self, global_person_ids: set[int], timestamp: float) -> None:
        for global_person_id in global_person_ids:
            self._upsert_person(global_person_id, timestamp)
            self._connection.execute(
                "UPDATE presence_sessions SET last_seen_time = ?, updated_at = ? WHERE global_person_id = ? AND status = 'inside'",
                (timestamp, time(), global_person_id),
            )

    def close_timed_out_sessions(self, timeout_minutes: int, now: float | None = None) -> TimeoutResult:
        if not self.store_personal_events:
            return TimeoutResult(0, None)
        with self._lock:
            return self._run_transaction(self._close_timed_out_sessions_tx, timeout_minutes, now)

    def _close_timed_out_sessions_tx(self, timeout_minutes: int, now: float | None = None) -> TimeoutResult:
        now = time() if now is None else now
        cutoff = now - (timeout_minutes * 60)
        closed = 0
        last_timeout_at: float | None = None
        rows = self._connection.execute(
            """
            SELECT session_id, global_person_id FROM presence_sessions
            WHERE status = 'inside' AND COALESCE(last_seen_time, entry_time, created_at) < ?
            """,
            (cutoff,),
        ).fetchall()
        for session_id, global_person_id in rows:
            exists = self._connection.execute("SELECT 1 FROM timeout_events WHERE session_id = ?", (session_id,)).fetchone()
            if exists:
                continue
            self._connection.execute(
                "UPDATE presence_sessions SET status = 'timeout', exit_time = ?, exit_reason = 'inactivity_timeout', updated_at = ? WHERE session_id = ? AND status = 'inside'",
                (now, now, session_id),
            )
            if self._connection.total_changes:
                self._connection.execute(
                    "INSERT OR IGNORE INTO timeout_events(session_id, global_person_id, timeout_at, timeout_minutes, created_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, global_person_id, now, timeout_minutes, now),
                )
                self._record_diagnostic_tx(
                    "info", "presence_timeout", "Session closed by inactivity timeout", global_person_id, session_id
                )
                closed += 1
                last_timeout_at = now
        if closed > 0:
            self._connection.execute(
                "UPDATE global_counts SET inside = CASE WHEN inside >= ? THEN inside - ? ELSE 0 END WHERE id = 1",
                (closed, closed),
            )
        return TimeoutResult(closed, last_timeout_at)

    def event_count(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) FROM counting_events").fetchone()
            return int(row[0])

    def table_names(self) -> list[str]:
        with self._lock:
            return [row[0] for row in self._connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]

    def purge_expired(self, now: float | None = None) -> dict[str, int]:
        """Delete granular records beyond the configured maximum retention period."""
        cutoff = (time() if now is None else now) - max(1, self.retention_hours) * 3600
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                deleted = {
                    "counting_events": self._connection.execute(
                        "DELETE FROM counting_events WHERE timestamp < ?", (cutoff,)
                    ).rowcount,
                    "presence_sessions": self._connection.execute(
                        "DELETE FROM presence_sessions WHERE updated_at < ?", (cutoff,)
                    ).rowcount,
                    "timeout_events": self._connection.execute(
                        "DELETE FROM timeout_events WHERE timeout_at < ?", (cutoff,)
                    ).rowcount,
                    "diagnostic_events": self._connection.execute(
                        "DELETE FROM diagnostic_events WHERE timestamp < ?", (cutoff,)
                    ).rowcount,
                    "global_persons": self._connection.execute(
                        "DELETE FROM global_persons WHERE last_seen_time < ?", (cutoff,)
                    ).rowcount,
                }
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        backup_cutoff = time() - max(1, self.retention_hours) * 3600
        for backup in self.path.parent.glob(f"{self.path.name}.backup_*.fernet"):
            try:
                if backup.stat().st_mtime < backup_cutoff:
                    backup.unlink()
            except OSError:
                pass
        return {name: max(0, count) for name, count in deleted.items()}

    def export_personal_data(self, limit: int = 1000) -> dict[str, object]:
        """Return an admin-only, machine-readable export without any image data."""
        limit = max(1, min(int(limit), 10_000))
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT timestamp, camera_id, global_person_id, direction, event_type,
                       counted, uncertain, consensus_reason, confidence, model_name
                FROM counting_events ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            events = [
                {
                    "timestamp": row[0],
                    "camera_id": self._plain_text(row[1]),
                    "pseudonymous_person_id": row[2],
                    "direction": row[3],
                    "event_type": row[4],
                    "counted": bool(row[5]),
                    "uncertain": bool(row[6]),
                    "reason": self._plain_text(row[7]),
                    "confidence": row[8],
                    "model": self._plain_text(row[9]),
                }
                for row in rows
            ]
            return {
                "exported_at": time(),
                "retention_hours": self.retention_hours,
                "images_included": False,
                "aggregate_counts": self.restore_counts(),
                "events": events,
            }

    def delete_personal_data(self, *, reset_aggregates: bool = False) -> dict[str, int]:
        """Erase all granular camera/person records; aggregate counts are optional."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                deleted: dict[str, int] = {}
                for table in (
                    "counting_events",
                    "presence_sessions",
                    "timeout_events",
                    "diagnostic_events",
                    "global_persons",
                    "camera_status",
                ):
                    deleted[table] = max(0, self._connection.execute(f"DELETE FROM {table}").rowcount)
                if reset_aggregates:
                    self._connection.execute(
                        "UPDATE global_counts SET entered = 0, exited = 0, inside = 0 WHERE id = 1"
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return deleted

    def _protect_existing_rows(self) -> None:
        marker = self._connection.execute(
            "SELECT value FROM app_settings WHERE key = 'data_protection_version'"
        ).fetchone()
        if marker and marker[0] == "1":
            return
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            person_ids = {
                int(row[0])
                for table in ("counting_events", "presence_sessions", "global_persons", "timeout_events", "diagnostic_events")
                for row in self._connection.execute(
                    f"SELECT DISTINCT global_person_id FROM {table} WHERE global_person_id IS NOT NULL"
                ).fetchall()
            }
            mapping = {value: self._protected_id("person", value) for value in person_ids}
            for old, new in mapping.items():
                for table in ("counting_events", "presence_sessions", "timeout_events", "diagnostic_events"):
                    self._connection.execute(
                        f"UPDATE {table} SET global_person_id = ? WHERE global_person_id = ?", (new, old)
                    )
                self._connection.execute(
                    "UPDATE global_persons SET global_person_id = ? WHERE global_person_id = ?", (new, old)
                )
            for row in self._connection.execute(
                "SELECT id, camera_id, local_track_id, passage_id, consensus_reason, model_name FROM counting_events"
            ).fetchall():
                self._connection.execute(
                    """
                    UPDATE counting_events SET camera_id=?, local_track_id=?, passage_id=?, consensus_reason=?, model_name=?
                    WHERE id=?
                    """,
                    (
                        self._protected_text(row[1]),
                        self._protected_id("track", row[2]),
                        self._protected_pseudonym("passage", row[3]),
                        self._protected_text(row[4]),
                        self._protected_text(row[5]),
                        row[0],
                    ),
                )
            for row in self._connection.execute(
                "SELECT session_id, entry_camera, exit_camera, exit_reason FROM presence_sessions"
            ).fetchall():
                self._connection.execute(
                    "UPDATE presence_sessions SET entry_camera=?, exit_camera=?, exit_reason=? WHERE session_id=?",
                    (self._protected_text(row[1]), self._protected_text(row[2]), self._protected_text(row[3]), row[0]),
                )
            for row in self._connection.execute("SELECT id, message, payload FROM diagnostic_events").fetchall():
                self._connection.execute(
                    "UPDATE diagnostic_events SET message=?, payload=? WHERE id=?",
                    (self._protected_text(row[1]), self._protected_text(row[2]), row[0]),
                )
            self._connection.execute(
                "INSERT OR REPLACE INTO app_settings(key, value, updated_at) VALUES('data_protection_version', '1', ?)",
                (time(),),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _upsert_person(self, global_person_id: int | None, timestamp: float) -> None:
        if global_person_id is None:
            return
        self._connection.execute(
            """
            INSERT INTO global_persons(global_person_id, first_seen_time, last_seen_time, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(global_person_id) DO UPDATE SET last_seen_time = excluded.last_seen_time, active = 1
            """,
            (global_person_id, timestamp, timestamp),
        )

    def _open_session(self, global_person_id: int, timestamp: float, camera_id: str, event_id: int, confidence: float) -> bool:
        open_row = self._connection.execute(
            "SELECT session_id FROM presence_sessions WHERE global_person_id = ? AND status = 'inside'",
            (global_person_id,),
        ).fetchone()
        if open_row:
            self._record_diagnostic_tx(
                "info", "duplicate_entry", "Entry ignored because an inside session is already open", global_person_id, int(open_row[0])
            )
            return False
        self._connection.execute(
            """
            INSERT INTO presence_sessions(global_person_id, entry_time, last_seen_time, status, entry_camera, entry_event_id, confidence, created_at, updated_at)
            VALUES (?, ?, ?, 'inside', ?, ?, ?, ?, ?)
            """,
            (global_person_id, timestamp, timestamp, self._protected_text(camera_id), event_id, confidence, time(), time()),
        )
        return True

    def _close_session(self, global_person_id: int, timestamp: float, camera_id: str, event_id: int, reason: str) -> bool:
        row = self._connection.execute(
            "SELECT session_id FROM presence_sessions WHERE global_person_id = ? AND status = 'inside' ORDER BY entry_time DESC LIMIT 1",
            (global_person_id,),
        ).fetchone()
        if not row:
            self._record_diagnostic_tx(
                "warning", "exit_without_open_session", "Exit ignored because no open inside session exists", global_person_id, None
            )
            return False
        session_id = int(row[0])
        self._connection.execute(
            """
            UPDATE presence_sessions
            SET exit_time = ?, status = 'outside', exit_reason = ?, exit_camera = ?, exit_event_id = ?, updated_at = ?
            WHERE session_id = ? AND status = 'inside'
            """,
            (timestamp, self._protected_text(reason), self._protected_text(camera_id), event_id, time(), session_id),
        )
        return True

    def _protected_text(self, value: str | None) -> str | None:
        return self.protector.encrypt_text(value) if self.protector else value

    def _protected_id(self, scope: str, value: int | None) -> int | None:
        return self.protector.pseudonymize_id(scope, value) if self.protector else value

    def _protected_pseudonym(self, scope: str, value: str | None) -> str | None:
        return self.protector.pseudonymize_text(scope, value) if self.protector else value

    def _plain_text(self, value: str | None) -> str | None:
        return self.protector.decrypt_text(value) if self.protector else value
