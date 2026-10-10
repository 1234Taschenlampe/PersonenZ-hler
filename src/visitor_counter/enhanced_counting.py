from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Callable

from .configuration import AppConfig
from .data_protection import DataProtector, load_data_protector
from .inference_pipeline import ProcessingPipeline
from .types import ConsensusDecision, CrossingEvent, Direction, TrackedObject

LOGGER = logging.getLogger(__name__)


def _locked_store(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def locked(self: DailyUniqueStore, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


class DailyUniqueStore:
    """Count a person at most once per local calendar day.

    Re-ID embeddings are kept only for the active day. If a data-protection key is
    configured, the active-day embeddings are persisted encrypted so a restart does
    not make the same visitor count twice. Old-day profiles are deleted immediately
    on rollover. Without a key the feature still works in RAM, but restart-safe
    deduplication is unavailable.
    """

    def __init__(
        self,
        project_root: Path,
        config: AppConfig,
        *,
        threshold: float | None = None,
        protector: DataProtector | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self._lock = RLock()
        self.threshold = float(
            config.identity.reid_threshold if threshold is None else threshold
        )
        self.threshold = max(0.50, min(0.99, self.threshold))
        self.protector = (
            protector
            if protector is not None
            else load_data_protector(config.database, project_root)
        )
        configured_database = Path(config.database.path).expanduser()
        data_dir = (
            configured_database.parent
            if configured_database.is_absolute()
            else (project_root / configured_database).parent
        )
        self.path = data_dir / "daily_unique.sqlite3"
        self._profiles: dict[int, tuple[float, ...]] = {}
        self._fallback_ids: set[int] = set()
        self._day = self._local_day(time())
        self._next_profile_id = 1
        self.degraded = self.protector is None
        self._connection: sqlite3.Connection | None = None
        if self.protector is not None:
            self._open_database()
            self._load_current_day()

    @staticmethod
    def _local_day(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).astimezone().date().isoformat()

    @property
    @_locked_store
    def count(self) -> int:
        return len(self._profiles) + len(self._fallback_ids)

    @property
    def persistent(self) -> bool:
        return self._connection is not None and self.protector is not None

    @_locked_store
    def ensure_day(self, timestamp: float | None = None) -> None:
        now = time() if timestamp is None else timestamp
        current = self._local_day(now)
        if current == self._day:
            return
        LOGGER.info("DAILY_UNIQUE_ROLLOVER previous=%s current=%s", self._day, current)
        self._day = current
        self._profiles.clear()
        self._fallback_ids.clear()
        self._next_profile_id = 1
        if self._connection is not None:
            self._connection.execute(
                "DELETE FROM daily_unique_profiles WHERE day <> ?", (self._day,)
            )
            self._connection.commit()
            self._load_current_day()

    @_locked_store
    def register(
        self,
        global_person_id: int,
        embedding: tuple[float, ...] | None,
        timestamp: float,
    ) -> bool:
        self.ensure_day(timestamp)
        if embedding:
            normalized = self._normalize(embedding)
            if normalized:
                best_id, best_score = self._best_match(normalized)
                if best_id is not None and best_score >= self.threshold:
                    self._touch_profile(best_id, timestamp)
                    LOGGER.info(
                        "DAILY_UNIQUE_MATCH profile=%s similarity=%.4f count=%s",
                        best_id,
                        best_score,
                        self.count,
                    )
                    return False
                profile_id = self._next_profile_id
                self._next_profile_id += 1
                self._profiles[profile_id] = normalized
                self._persist_profile(profile_id, normalized, timestamp)
                LOGGER.info(
                    "DAILY_UNIQUE_NEW profile=%s count=%s", profile_id, self.count
                )
                return True

        # A missing embedding should not silently lose a real visitor. This fallback
        # is process-local and therefore marked degraded. With OSNet enabled it
        # should only be used for occasional failed crops/inference calls.
        self.degraded = True
        if global_person_id in self._fallback_ids:
            return False
        self._fallback_ids.add(global_person_id)
        LOGGER.warning(
            "DAILY_UNIQUE_FALLBACK global_id=%s count=%s", global_person_id, self.count
        )
        return True

    @_locked_store
    def reset(self) -> None:
        self._profiles.clear()
        self._fallback_ids.clear()
        self._next_profile_id = 1
        self._day = self._local_day(time())
        if self._connection is not None:
            self._connection.execute("DELETE FROM daily_unique_profiles")
            self._connection.commit()

    @_locked_store
    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _open_database(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        # Constructed by the service/GUI thread, used by inference and reset
        # callbacks. The reentrant store lock serializes access across threads.
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.execute("PRAGMA secure_delete=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_unique_profiles (
                profile_id INTEGER PRIMARY KEY,
                day TEXT NOT NULL,
                embedding TEXT NOT NULL,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_unique_day ON daily_unique_profiles(day)"
        )
        self._connection.commit()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _load_current_day(self) -> None:
        if self._connection is None or self.protector is None:
            return
        self._connection.execute(
            "DELETE FROM daily_unique_profiles WHERE day <> ?", (self._day,)
        )
        rows = self._connection.execute(
            "SELECT profile_id, embedding FROM daily_unique_profiles WHERE day = ? ORDER BY profile_id",
            (self._day,),
        ).fetchall()
        self._profiles.clear()
        highest = 0
        for profile_id, encrypted in rows:
            try:
                decoded = self.protector.decrypt_text(str(encrypted))
                vector = tuple(float(value) for value in json.loads(decoded or "[]"))
                normalized = self._normalize(vector)
                if normalized:
                    self._profiles[int(profile_id)] = normalized
                    highest = max(highest, int(profile_id))
            except (ValueError, TypeError, json.JSONDecodeError):
                LOGGER.warning(
                    "Ignoring unreadable daily ReID profile id=%s", profile_id
                )
        self._next_profile_id = highest + 1
        self._connection.commit()

    def _persist_profile(
        self, profile_id: int, embedding: tuple[float, ...], timestamp: float
    ) -> None:
        if self._connection is None or self.protector is None:
            return
        serialized = json.dumps(embedding, separators=(",", ":"))
        encrypted = self.protector.encrypt_text(serialized)
        self._connection.execute(
            """
            INSERT INTO daily_unique_profiles(profile_id, day, embedding, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, self._day, encrypted, timestamp, timestamp),
        )
        self._connection.commit()

    def _touch_profile(self, profile_id: int, timestamp: float) -> None:
        if self._connection is None:
            return
        self._connection.execute(
            "UPDATE daily_unique_profiles SET last_seen = ? WHERE profile_id = ? AND day = ?",
            (timestamp, profile_id, self._day),
        )
        self._connection.commit()

    def _best_match(self, embedding: tuple[float, ...]) -> tuple[int | None, float]:
        best_id: int | None = None
        best_score = -1.0
        for profile_id, candidate in self._profiles.items():
            if len(candidate) != len(embedding):
                continue
            score = sum(a * b for a, b in zip(candidate, embedding))
            if score > best_score:
                best_id = profile_id
                best_score = score
        return best_id, best_score

    @staticmethod
    def _normalize(embedding: tuple[float, ...]) -> tuple[float, ...] | None:
        if not embedding:
            return None
        norm = math.sqrt(sum(value * value for value in embedding))
        if norm <= 1e-8:
            return None
        return tuple(value / norm for value in embedding)


class _IdentityObserver:
    def __init__(
        self, delegate: Any, callback: Callable[[list[TrackedObject]], None]
    ) -> None:
        self._delegate = delegate
        self._callback = callback

    def update(self, *args: Any, **kwargs: Any) -> list[TrackedObject]:
        tracks = self._delegate.update(*args, **kwargs)
        self._callback(tracks)
        return tracks

    def reset(self) -> None:
        self._delegate.reset()

    @property
    def global_visible(self) -> int:
        return self._delegate.global_visible

    @property
    def visible_global_ids(self) -> set[int]:
        return self._delegate.visible_global_ids

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class _ConsensusObserver:
    def __init__(
        self,
        delegate: Any,
        callback: Callable[[CrossingEvent, ConsensusDecision], None],
    ) -> None:
        self._delegate = delegate
        self._callback = callback

    def decide(self, event: CrossingEvent) -> ConsensusDecision:
        decision = self._delegate.decide(event)
        self._callback(event, decision)
        return decision

    def reset(self) -> None:
        self._delegate.reset()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class EnhancedProcessingPipeline(ProcessingPipeline):
    """Event-driven production counters layered on the existing inference pipeline.

    Semantics:
    - inside: current occupancy, +1 on a confirmed IN crossing, -1 on OUT
    - entered/exited: persistent confirmed passages by direction
    - daily_unique: each ReID profile counts once per local day
    - throughput: entered + exited, exposed as a derived GUI/API value
    """

    def __init__(
        self, config: AppConfig, project_root: Path, *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(config, project_root, *args, **kwargs)
        self._latest_embeddings_by_global_id: dict[int, tuple[float, ...]] = {}
        self.daily_unique_store = DailyUniqueStore(project_root, config)
        self.global_counts.daily_unique = self.daily_unique_store.count
        self.global_counts.daily_unique_degraded = self.daily_unique_store.degraded
        self.identity = _IdentityObserver(self.identity, self._remember_embeddings)
        self.consensus = _ConsensusObserver(
            self.consensus, self._apply_confirmed_crossing
        )

    def run(self) -> None:
        try:
            super().run()
        finally:
            self.daily_unique_store.close()

    def _remember_embeddings(self, tracks: list[TrackedObject]) -> None:
        for track in tracks:
            if (
                track.global_person_id is None
                or track.embedding is None
                or track.lost_frames != 0
            ):
                continue
            self._latest_embeddings_by_global_id[track.global_person_id] = (
                track.embedding
            )
        if len(self._latest_embeddings_by_global_id) > 10000:
            # The daily store is the durable active-day memory. This cache only needs
            # recent IDs to attach the current crossing event to its embedding.
            for key in list(self._latest_embeddings_by_global_id)[:5000]:
                del self._latest_embeddings_by_global_id[key]

    def _apply_confirmed_crossing(
        self, event: CrossingEvent, decision: ConsensusDecision
    ) -> None:
        if event.global_person_id is None or decision.uncertain:
            self.global_counts.uncertain_consensus += 1
            return
        if not decision.counted:
            self.global_counts.suppressed_duplicates += 1
            return
        if event.direction is Direction.UNKNOWN:
            self.global_counts.wrong_way += 1
        elif event.direction is Direction.IN:
            self.global_counts.entered += 1
            self.global_counts.inside += 1
            embedding = self._latest_embeddings_by_global_id.get(
                event.global_person_id or -1
            )
            self.daily_unique_store.register(
                event.global_person_id or -1, embedding, event.timestamp
            )
            self.global_counts.daily_unique = self.daily_unique_store.count
            self.global_counts.daily_unique_degraded = self.daily_unique_store.degraded
        elif event.direction is Direction.OUT:
            self.global_counts.exited += 1
            self.global_counts.inside = max(0, self.global_counts.inside - 1)
        self._persist_global_counts()
        LOGGER.info(
            "PRODUCTION_COUNTER inside=%s unique_today=%s entries=%s exits=%s throughput=%s",
            self.global_counts.inside,
            getattr(self.global_counts, "daily_unique", 0),
            self.global_counts.entered,
            self.global_counts.exited,
            self.global_counts.entered + self.global_counts.exited,
        )

    def _sync_live_presence_counts(
        self, visible_ids: set[int], timestamp: float
    ) -> None:
        # Visibility is useful diagnostic information, but it must not alter occupancy.
        # Occupancy changes only when a validated line-crossing event is accepted.
        _ = visible_ids, timestamp

    def _emit_stats(self) -> None:
        self.daily_unique_store.ensure_day()
        self.global_counts.daily_unique = self.daily_unique_store.count
        self.global_counts.daily_unique_degraded = self.daily_unique_store.degraded
        super()._emit_stats()

    def reset_counts(self) -> None:
        super().reset_counts()
        self.daily_unique_store.reset()
        self._latest_embeddings_by_global_id.clear()
        self.global_counts.daily_unique = 0
        self.global_counts.daily_unique_degraded = self.daily_unique_store.degraded


def install_enhanced_gui(gui_module: Any) -> None:
    """Patch the existing GUI without duplicating its camera/settings implementation."""

    main_window = gui_module.MainWindow
    if getattr(main_window, "_enhanced_counter_ui_installed", False):
        return

    original_stats_ready = main_window._on_stats_ready
    original_write_live_status = main_window._write_live_status

    def build_counts_panel(self: Any) -> Any:
        panel = gui_module.QGroupBox("Zaehlwerte")
        grid = gui_module.QGridLayout(panel)
        items = [
            ("global_inside", "Aktuell im Gebaeude"),
            ("daily_unique", "Besucher heute (eindeutig)"),
            ("throughput", "Durchfluss gesamt"),
            ("global_in", "Eintritte gesamt"),
            ("global_out", "Austritte gesamt"),
            ("camera_1_in", "Kamera 1 Eintritte"),
            ("camera_1_out", "Kamera 1 Austritte"),
            ("camera_1_visible", "Kamera 1 sichtbar"),
            ("camera_2_in", "Kamera 2 Eintritte"),
            ("camera_2_out", "Kamera 2 Austritte"),
            ("camera_2_visible", "Kamera 2 sichtbar"),
            ("suppressed", "Unterdrueckte Doppelzaehlungen"),
            ("uncertain", "Unsichere Ereignisse"),
        ]
        for index, (key, title) in enumerate(items):
            value = gui_module.QLabel("0")
            value.setStyleSheet("font-size:24px;font-weight:bold;")
            self.count_labels[key] = value
            grid.addWidget(gui_module.QLabel(title), index // 3 * 2, index % 3)
            grid.addWidget(value, index // 3 * 2 + 1, index % 3)
        return panel

    def on_stats_ready(self: Any, stats: Any, counts: Any) -> None:
        original_stats_ready(self, stats, counts)
        self.count_labels["daily_unique"].setText(
            str(getattr(counts, "daily_unique", 0))
        )
        self.count_labels["throughput"].setText(
            str(int(counts.entered) + int(counts.exited))
        )
        degraded = bool(getattr(counts, "daily_unique_degraded", False))
        tooltip = (
            "Tages-ReID laeuft nur im RAM bzw. ohne restart-sichere Verschluesselung."
            if degraded
            else "Tages-ReID-Profile werden verschluesselt gespeichert und beim Tageswechsel geloescht."
        )
        self.count_labels["daily_unique"].setToolTip(tooltip)

    def write_live_status(self: Any, stats: Any, counts: Any) -> None:
        before = getattr(self, "_last_live_status_write_at", 0.0)
        original_write_live_status(self, stats, counts)
        after = getattr(self, "_last_live_status_write_at", 0.0)
        if after == before or not self.live_status_path.exists():
            return
        try:
            payload = json.loads(self.live_status_path.read_text(encoding="utf-8"))
            payload.setdefault("counts", {})["daily_unique"] = int(
                getattr(counts, "daily_unique", 0)
            )
            payload["counts"]["throughput"] = int(counts.entered) + int(counts.exited)
            payload["counts"]["daily_unique_degraded"] = bool(
                getattr(counts, "daily_unique_degraded", False)
            )
            tmp = self.live_status_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            tmp.replace(self.live_status_path)
        except (OSError, ValueError, TypeError) as exc:
            LOGGER.warning("ENHANCED_LIVE_STATUS_WRITE_FAILED error=%s", exc)

    main_window._build_counts_panel = build_counts_panel
    main_window._on_stats_ready = on_stats_ready
    main_window._write_live_status = write_live_status
    main_window._enhanced_counter_ui_installed = True
