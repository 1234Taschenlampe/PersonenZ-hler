from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

from visitor_counter.configuration import AppConfig
from visitor_counter.enhanced_counting import DailyUniqueStore


def test_daily_unique_counts_same_embedding_once_and_persists(tmp_path: Path, monkeypatch) -> None:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("VISITOR_COUNTER_DATA_KEY", key)
    config = AppConfig()
    config.identity.reid_threshold = 0.80

    timestamp = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
    first = (1.0, 0.0, 0.0)
    same_person = (0.995, 0.05, 0.0)
    other_person = (0.0, 1.0, 0.0)

    store = DailyUniqueStore(tmp_path, config)
    assert store.register(1, first, timestamp) is True
    assert store.register(2, same_person, timestamp + 10) is False
    assert store.register(3, other_person, timestamp + 20) is True
    assert store.count == 2
    assert store.persistent is True
    store.close()

    reopened = DailyUniqueStore(tmp_path, config)
    assert reopened.count == 2
    assert reopened.register(99, first, timestamp + 30) is False
    assert reopened.count == 2
    reopened.close()


def test_daily_unique_resets_on_next_local_day(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VISITOR_COUNTER_DATA_KEY", Fernet.generate_key().decode("ascii"))
    config = AppConfig()
    config.identity.reid_threshold = 0.80
    start = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)

    store = DailyUniqueStore(tmp_path, config)
    assert store.register(1, (1.0, 0.0), start.timestamp()) is True
    assert store.count == 1

    next_day = start + timedelta(days=1)
    assert store.register(2, (1.0, 0.0), next_day.timestamp()) is True
    assert store.count == 1
    store.close()


def test_daily_unique_falls_back_without_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("VISITOR_COUNTER_DATA_KEY", raising=False)
    config = AppConfig()

    store = DailyUniqueStore(tmp_path, config)
    now = datetime.now().astimezone().timestamp()
    assert store.register(7, None, now) is True
    assert store.register(7, None, now + 1) is False
    assert store.degraded is True
    assert store.persistent is False
    store.close()
