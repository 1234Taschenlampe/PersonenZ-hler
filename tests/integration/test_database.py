from __future__ import annotations

from pathlib import Path

from visitor_counter.database import EventDatabase
from visitor_counter.types import BoundingBox, ConsensusDecision, CrossingEvent, Direction


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
    duplicate = db.record_decision(ConsensusDecision(entry, True, None, False, "ok"), "YOLO26x")
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
    db.record_decision(ConsensusDecision(exit_event, True, None, False, "ok"), "YOLO26x")
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
    db.record_decision(ConsensusDecision(exit_event, True, None, False, "ok"), "YOLO26x")
    counts = db.restore_counts()
    assert counts["inside"] == 0
    assert counts["exited"] == 0
    db.close()


def test_set_global_counts_persists_live_counter_snapshot(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3")
    db.set_global_counts(entered=3, exited=1, inside=2)

    counts = db.restore_counts()
    assert counts["entered"] == 3
    assert counts["exited"] == 1
    assert counts["inside"] == 2
    db.close()
