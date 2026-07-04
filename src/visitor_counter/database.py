from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import sqlite3
import threading
from time import time

from .types import ConsensusDecision, Direction

LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class TimeoutResult:
    closed_sessions: int
    last_timeout_at: float | None


class EventDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

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
        if "app_settings" in tables:
            try:
                row = self._connection.execute("SELECT value FROM app_settings WHERE key = 'schema_version'").fetchone()
                if row:
                    schema_version = int(row[0])
            except sqlite3.OperationalError:
                pass
        elif "presence_sessions" in tables:
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(presence_sessions)").fetchall()}
            if "id" in columns and "session_id" not in columns:
                schema_version = 1

        # Backup the database file if migrating from version 1
        if self.path.exists() and schema_version == 1:
            import shutil
            backup_path = self.path.parent / f"{self.path.name}.backup_{int(time())}"
            try:
                shutil.copy2(self.path, backup_path)
                LOGGER.info("DATABASE_MIGRATION_BACKUP created at: %s", backup_path)
            except Exception as e:
                LOGGER.error("DATABASE_MIGRATION_BACKUP_FAILED: %s", e)

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
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_global ON counting_events(global_person_id, timestamp)")
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
        with self._lock:
            return self._run_transaction(self._record_decision_tx, decision, model_name, processing_ms)

    def _record_decision_tx(self, decision: ConsensusDecision, model_name: str, processing_ms: float | None = None) -> int:
        event = decision.event
        cursor = self._connection.execute(
            """
            INSERT OR IGNORE INTO counting_events (
                timestamp, camera_id, local_track_id, global_person_id, session_id, passage_id,
                direction, event_type, counted, uncertain, consensus_reason, confidence, model_name, processing_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.timestamp,
                event.camera_id,
                event.local_track_id,
                event.global_person_id,
                event.session_id,
                event.passage_id,
                event.direction.value,
                "uncertain" if decision.uncertain else "crossing",
                int(decision.counted),
                int(decision.uncertain),
                decision.reason,
                event.confidence,
                model_name,
                processing_ms,
                time(),
            ),
        )
        if cursor.rowcount == 0:
            self.record_diagnostic("info", "duplicate_passage_event", "Duplicate passage event suppressed", event.global_person_id, event.session_id)
            return 0
        event_id = int(cursor.lastrowid)
        self._upsert_person(event.global_person_id, event.timestamp)
        if decision.counted and not decision.uncertain and event.global_person_id is not None:
            if event.direction == Direction.IN:
                if self._open_session(event.global_person_id, event.timestamp, event.camera_id, event_id, event.confidence):
                    self._connection.execute(
                        "UPDATE global_counts SET entered = entered + 1, inside = inside + 1 WHERE id = 1"
                    )
                else:
                    self._connection.execute("UPDATE counting_events SET counted = 0, event_type = 'duplicate_entry' WHERE id = ?", (event_id,))
            elif event.direction == Direction.OUT:
                if self._close_session(event.global_person_id, event.timestamp, event.camera_id, event_id, "camera_exit"):
                    self._connection.execute(
                        "UPDATE global_counts SET exited = exited + 1, inside = CASE WHEN inside > 0 THEN inside - 1 ELSE 0 END WHERE id = 1"
                    )
                else:
                    self._connection.execute("UPDATE counting_events SET counted = 0, event_type = 'orphan_exit' WHERE id = ?", (event_id,))
        elif decision.uncertain:
            self.record_diagnostic("warning", "uncertain_event", decision.reason, event.global_person_id, event.session_id)
        return event_id

    def record_diagnostic(self, severity: str, code: str, message: str, global_person_id: int | None = None, session_id: int | None = None) -> None:
        with self._lock:
            self._run_transaction(self._record_diagnostic_tx, severity, code, message, global_person_id, session_id)

    def _record_diagnostic_tx(self, severity: str, code: str, message: str, global_person_id: int | None = None, session_id: int | None = None) -> None:
        self._connection.execute(
            """
            INSERT INTO diagnostic_events(timestamp, severity, code, message, global_person_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (time(), severity, code, message, global_person_id, session_id),
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

    def update_last_seen(self, global_person_ids: set[int], timestamp: float) -> None:
        with self._lock:
            self._run_transaction(self._update_last_seen_tx, global_person_ids, timestamp)

    def _update_last_seen_tx(self, global_person_ids: set[int], timestamp: float) -> None:
        for global_person_id in global_person_ids:
            self._upsert_person(global_person_id, timestamp)
            self._connection.execute(
                "UPDATE presence_sessions SET last_seen_time = ?, updated_at = ? WHERE global_person_id = ? AND status = 'inside'",
                (timestamp, time(), global_person_id),
            )

    def close_timed_out_sessions(self, timeout_minutes: int, now: float | None = None) -> TimeoutResult:
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
                self.record_diagnostic("info", "presence_timeout", "Session closed by inactivity timeout", global_person_id, session_id)
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
            self.record_diagnostic("info", "duplicate_entry", "Entry ignored because an inside session is already open", global_person_id, int(open_row[0]))
            return False
        self._connection.execute(
            """
            INSERT INTO presence_sessions(global_person_id, entry_time, last_seen_time, status, entry_camera, entry_event_id, confidence, created_at, updated_at)
            VALUES (?, ?, ?, 'inside', ?, ?, ?, ?, ?)
            """,
            (global_person_id, timestamp, timestamp, camera_id, event_id, confidence, time(), time()),
        )
        return True

    def _close_session(self, global_person_id: int, timestamp: float, camera_id: str, event_id: int, reason: str) -> bool:
        row = self._connection.execute(
            "SELECT session_id FROM presence_sessions WHERE global_person_id = ? AND status = 'inside' ORDER BY entry_time DESC LIMIT 1",
            (global_person_id,),
        ).fetchone()
        if not row:
            self.record_diagnostic("warning", "exit_without_open_session", "Exit ignored because no open inside session exists", global_person_id, None)
            return False
        session_id = int(row[0])
        self._connection.execute(
            """
            UPDATE presence_sessions
            SET exit_time = ?, status = 'outside', exit_reason = ?, exit_camera = ?, exit_event_id = ?, updated_at = ?
            WHERE session_id = ? AND status = 'inside'
            """,
            (timestamp, reason, camera_id, event_id, time(), session_id),
        )
        return True
