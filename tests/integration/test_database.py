from __future__ import annotations

import sqlite3
from pathlib import Path

from visitor_counter.database import EventDatabase
from visitor_counter.types import (
    BoundingBox,
    ConsensusDecision,
    CrossingEvent,
    Direction,
)


def test_database_records_event(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3")
    event = CrossingEvent(
        camera_id="camera_1",
        local_track_id=7,
        direction=Direction.IN,
        timestamp=1.0,
        zone="entry",
        bbox=BoundingBox(0, 0, 10, 10),
        confidence=0.8,
    )
    db.record_decision(ConsensusDecision(event, True, None, False, "test"), "YOLO26x")
    assert db.event_count() == 1
    db.close()


def test_entry_and_exit_update_sessions_once(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3")
    entry = CrossingEvent(
        camera_id="camera_1",
        local_track_id=1,
        global_person_id=42,
        passage_id="42:entry:1",
        direction=Direction.IN,
        timestamp=1.0,
        zone="entry",
        bbox=BoundingBox(0, 0, 10, 10),
        confidence=0.9,
    )
    db.record_decision(ConsensusDecision(entry, True, None, False, "ok"), "YOLO26x")
    assert db.restore_counts()["inside"] == 1
    duplicate = db.record_decision(
        ConsensusDecision(entry, True, None, False, "ok"), "YOLO26x"
    )
    assert duplicate == 0
    assert db.restore_counts()["inside"] == 1
    exit_event = CrossingEvent(
        camera_id="camera_2",
        local_track_id=2,
        global_person_id=42,
        passage_id="42:exit:1",
        direction=Direction.OUT,
        timestamp=2.0,
        zone="exit",
        bbox=BoundingBox(0, 0, 10, 10),
        confidence=0.9,
    )
    db.record_decision(
        ConsensusDecision(exit_event, True, None, False, "ok"), "YOLO26x"
    )
    counts = db.restore_counts()
    assert counts["inside"] == 0
    assert counts["entered"] == 1
    assert counts["exited"] == 1
    db.close()


def test_exit_without_session_is_orphan_and_does_not_count(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3")
    exit_event = CrossingEvent(
        camera_id="camera_2",
        local_track_id=2,
        global_person_id=7,
        passage_id="7:exit:1",
        direction=Direction.OUT,
        timestamp=2.0,
        zone="exit",
        bbox=BoundingBox(0, 0, 10, 10),
        confidence=0.9,
    )
    db.record_decision(
        ConsensusDecision(exit_event, True, None, False, "ok"), "YOLO26x"
    )
    counts = db.restore_counts()
    assert counts["inside"] == 0
    assert counts["exited"] == 0
    db.close()


def test_set_global_counts_persists_live_counter_snapshot(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3")
    db.set_global_counts(entered=3, exited=1, inside=2, wrong_way=4)

    counts = db.restore_counts()
    assert counts["entered"] == 3
    assert counts["exited"] == 1
    assert counts["inside"] == 2
    assert counts["wrong_way"] == 4
    db.close()


def test_wrong_way_event_has_distinct_type_and_does_not_change_occupancy(
    tmp_path: Path,
) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3")
    event = CrossingEvent(
        camera_id="camera_1",
        local_track_id=8,
        global_person_id=42,
        passage_id="42:wrong-way:1",
        direction=Direction.UNKNOWN,
        timestamp=3.0,
        zone="wrong_way",
        bbox=BoundingBox(0, 0, 10, 10),
        confidence=0.9,
    )

    db.record_decision(ConsensusDecision(event, True, None, False, "ok"), "YOLO26m")

    row = db._connection.execute(  # noqa: SLF001 - verifies persisted event semantics
        "SELECT event_type FROM counting_events"
    ).fetchone()
    assert row == ("wrong_way",)
    assert db.restore_counts()["inside"] == 0
    db.close()


def test_upgrade_adds_wrong_way_column_without_losing_counts(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE global_counts (id INTEGER PRIMARY KEY, entered INTEGER NOT NULL, exited INTEGER NOT NULL, inside INTEGER NOT NULL)"
    )
    connection.execute("INSERT INTO global_counts VALUES (1, 9, 4, 5)")
    connection.commit()
    connection.close()

    db = EventDatabase(path)

    assert db.restore_counts() == {
        "inside": 5,
        "entered": 9,
        "exited": 4,
        "wrong_way": 0,
        "timeouts": 0,
        "uncertain": 0,
        "suppressed": 0,
    }
    db.close()
