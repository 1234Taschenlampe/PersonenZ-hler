from __future__ import annotations

import logging
from pathlib import Path
from time import time

from cryptography.fernet import Fernet
import numpy as np

from visitor_counter.configuration import AppConfig, privacy_readiness_errors
from visitor_counter.data_protection import DataProtector
from visitor_counter.database import EventDatabase
from visitor_counter.logging_setup import SensitiveDataFilter
from visitor_counter.privacy import anonymize_frame, hidden_preview
from visitor_counter.types import BoundingBox, ConsensusDecision, CrossingEvent, Direction


def _event(timestamp: float | None = None) -> CrossingEvent:
    return CrossingEvent(
        camera_id="private-camera-name",
        local_track_id=7,
        global_person_id=42,
        passage_id="person-42-passage",
        direction=Direction.IN,
        timestamp=time() if timestamp is None else timestamp,
        zone="entry",
        bbox=BoundingBox(0, 0, 10, 10),
        confidence=0.9,
    )


def test_privacy_readiness_fails_closed_until_operator_documents_context() -> None:
    config = AppConfig()
    errors = privacy_readiness_errors(config)
    assert any("notice" in error.lower() for error in errors)
    assert any("legal basis" in error.lower() for error in errors)
    assert any("controller" in error.lower() for error in errors)

    config.privacy.privacy_notice_acknowledged = True
    config.privacy.privacy_notice_acknowledged_at = "2026-07-13T20:00:00+02:00"
    config.privacy.legal_basis = "documented assessment"
    config.privacy.controller_name = "Example Controller"
    config.privacy.controller_contact = "privacy@example.invalid"
    assert privacy_readiness_errors(config) == []


def test_full_frame_anonymization_and_hidden_preview_remove_detail() -> None:
    frame = np.arange(64 * 64 * 3, dtype=np.uint8).reshape((64, 64, 3))
    anonymized = anonymize_frame(frame, mode="full_frame", pixel_size=16)
    assert anonymized.shape == frame.shape
    assert not np.array_equal(anonymized, frame)
    assert len(np.unique(anonymized.reshape(-1, 3), axis=0)) <= 16

    hidden = hidden_preview(frame)
    assert hidden.shape == frame.shape
    assert not np.array_equal(hidden, frame)


def test_encrypted_event_storage_uses_pseudonyms_and_decrypts_admin_export(tmp_path: Path) -> None:
    protector = DataProtector.from_key(Fernet.generate_key().decode("ascii"))
    db = EventDatabase(
        tmp_path / "events.sqlite3",
        protector=protector,
        require_encryption=True,
        retention_hours=24,
    )
    db.record_decision(ConsensusDecision(_event(), True, None, False, "approved"), "private-model-name")
    row = db._connection.execute(  # noqa: SLF001 - verify encryption at the storage boundary
        "SELECT camera_id, local_track_id, global_person_id, passage_id, consensus_reason, model_name FROM counting_events"
    ).fetchone()
    assert row[0].startswith("enc:v1:")
    assert row[1] != 7
    assert row[2] != 42
    assert row[3].startswith("hmac:v1:")
    assert row[4].startswith("enc:v1:")
    assert row[5].startswith("enc:v1:")

    exported = db.export_personal_data()
    assert exported["images_included"] is False
    assert exported["events"][0]["camera_id"] == "private-camera-name"
    assert exported["events"][0]["reason"] == "approved"
    db.close()


def test_secure_default_discards_granular_events_but_keeps_aggregate_counts(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3", store_personal_events=False)
    assert db.record_decision(ConsensusDecision(_event(), True, None, False, "approved"), "model") == 0
    db.set_global_counts(entered=4, exited=1, inside=3)
    assert db.event_count() == 0
    assert db.restore_counts()["inside"] == 3
    db.close()


def test_retention_deletes_expired_personal_events(tmp_path: Path) -> None:
    db = EventDatabase(tmp_path / "events.sqlite3", retention_hours=1)
    db.record_decision(ConsensusDecision(_event(timestamp=time() - 7200), True, None, False, "old"), "model")
    deleted = db.purge_expired()
    assert deleted["counting_events"] == 1
    assert db.event_count() == 0
    db.close()


def test_log_filter_removes_image_derived_identifiers() -> None:
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "track_id=42 bbox=(1, 2, 3, 4) center=(5, 6) token=supersecret",
        (),
        None,
    )
    assert SensitiveDataFilter().filter(record)
    message = record.getMessage()
    assert "42" not in message
    assert "(1, 2, 3, 4)" not in message
    assert "(5, 6)" not in message
    assert "supersecret" not in message
