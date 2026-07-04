from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from time import time

from .types import ConsensusDecision, Direction


@dataclass(frozen=True)
class TimeoutResult:
    closed_sessions: int
    last_timeout_at: float | None


class EventDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def _migrate(self) -> None:
        with self._connection:
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
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_open ON presence_sessions(global_person_id, status)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_global ON counting_events(global_person_id, timestamp)")
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_counting_events_person_passage_type
                ON counting_events(global_person_id, passage_id, event_type)
                WHERE global_person_id IS NOT NULL AND passage_id IS NOT NULL
                """
            )

    def _add_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row[1] for row in self._connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def record_decision(self, decision: ConsensusDecision, model_name: str, processing_ms: float | None = None) -> int:
        event = decision.event
        with self._connection:
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
                if event.direction is Direction.IN:
                    if not self._open_session(event.global_person_id, event.timestamp, event.camera_id, event_id, event.confidence):
                        self._connection.execute("UPDATE counting_events SET counted = 0, event_type = 'duplicate_entry' WHERE id = ?", (event_id,))
                elif event.direction is Direction.OUT:
                    if not self._close_session(event.global_person_id, event.timestamp, event.camera_id, event_id, "camera_exit"):
                        self._connection.execute("UPDATE counting_events SET counted = 0, event_type = 'orphan_exit' WHERE id = ?", (event_id,))
            elif decision.uncertain:
                self.record_diagnostic("warning", "uncertain_event", decision.reason, event.global_person_id, event.session_id)
        return event_id

    def record_diagnostic(self, severity: str, code: str, message: str, global_person_id: int | None = None, session_id: int | None = None) -> None:
        self._connection.execute(
            """
            INSERT INTO diagnostic_events(timestamp, severity, code, message, global_person_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (time(), severity, code, message, global_person_id, session_id),
        )

    def restore_counts(self) -> dict[str, int]:
        row = self._connection.execute("SELECT COUNT(*) FROM presence_sessions WHERE status = 'inside'").fetchone()
        entered = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE counted = 1 AND uncertain = 0 AND direction = 'in'").fetchone()
        exited = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE counted = 1 AND uncertain = 0 AND direction = 'out'").fetchone()
        timeouts = self._connection.execute("SELECT COUNT(*) FROM timeout_events").fetchone()
        uncertain = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE uncertain = 1").fetchone()
        suppressed = self._connection.execute("SELECT COUNT(*) FROM counting_events WHERE counted = 0").fetchone()
        return {
            "inside": int(row[0]),
            "entered": int(entered[0]),
            "exited": int(exited[0]),
            "timeouts": int(timeouts[0]),
            "uncertain": int(uncertain[0]),
            "suppressed": int(suppressed[0]),
        }

    def update_last_seen(self, global_person_ids: set[int], timestamp: float) -> None:
        with self._connection:
            for global_person_id in global_person_ids:
                self._upsert_person(global_person_id, timestamp)
                self._connection.execute(
                    "UPDATE presence_sessions SET last_seen_time = ?, updated_at = ? WHERE global_person_id = ? AND status = 'inside'",
                    (timestamp, time(), global_person_id),
                )

    def close_timed_out_sessions(self, timeout_minutes: int, now: float | None = None) -> TimeoutResult:
        now = time() if now is None else now
        cutoff = now - (timeout_minutes * 60)
        closed = 0
        last_timeout_at: float | None = None
        with self._connection:
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
        return TimeoutResult(closed, last_timeout_at)

    def event_count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM counting_events").fetchone()
        return int(row[0])

    def table_names(self) -> list[str]:
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
