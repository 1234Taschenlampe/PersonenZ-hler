from datetime import datetime, timedelta
from pathlib import Path
from time import time
from types import SimpleNamespace
import json
import sqlite3

import pytest

from visitor_counter.application_service import ApplicationService
from visitor_counter.configuration import AppConfig
from visitor_counter.runtime_paths import RuntimePaths


def service(tmp_path):
    paths = RuntimePaths.discover(tmp_path, environ={})
    config = AppConfig()
    config.database.path = str(tmp_path / "counts.sqlite3")
    connection = sqlite3.connect(config.database.path)
    connection.executescript(
        "CREATE TABLE global_counts (id, entered, exited, inside, wrong_way);"
        "INSERT INTO global_counts VALUES(1,1,1,1,0);"
        "CREATE TABLE counting_events (timestamp, direction, counted, uncertain);"
    )
    connection.commit()
    connection.close()
    app = ApplicationService(paths, service_manager=SimpleNamespace(status=lambda: None))
    app.license_service = SimpleNamespace(inspect=lambda: None)
    app.config = lambda: config
    return app, config


def test_saved_occupancy_offset_survives_even_when_live_visibility_or_totals_disagree(tmp_path):
    app, config = service(tmp_path)
    app.paths.data_dir.mkdir(exist_ok=True)
    app.paths.live_status_file.write_text(json.dumps({
        "timestamp": time(), "counts": {"inside": 999, "entered": 500, "visible": 2},
        "runtime": {}, "cameras": [],
    }))
    before = Path(config.database.path).read_bytes()
    snapshot = app.snapshot()
    assert snapshot.counts["inside"] == 1
    assert snapshot.counts["entered"] == snapshot.counts["exited"] == 1
    assert snapshot.counts["occupancy_adjustment"] == 1
    assert snapshot.counts["throughput"] == 2
    assert snapshot.live_people.total is None
    assert Path(config.database.path).read_bytes() == before


def test_today_passages_exclude_yesterday_suppressed_and_uncertain_events(tmp_path):
    app, config = service(tmp_path)
    config.database.store_events = True
    noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    with sqlite3.connect(config.database.path) as connection:
        connection.executemany("INSERT INTO counting_events VALUES(?,?,?,?)", [
            ((noon - timedelta(days=1)).timestamp(), "in", 1, 0),
            (noon.timestamp(), "in", 1, 0), (noon.timestamp(), "OUT", 1, 0),
            (noon.timestamp(), "in", 0, 0), (noon.timestamp(), "out", 1, 1),
        ])
    assert app._today_passages(config) == {"today_entered": 1, "today_exited": 1}
    config.database.store_events = False
    assert app._today_passages(config) == {"today_entered": None, "today_exited": None}


def test_unreadable_counter_database_never_falls_back_to_a_fake_zero(tmp_path):
    app, config = service(tmp_path)
    Path(config.database.path).write_bytes(b"not a database")
    snapshot = app.snapshot()
    assert snapshot.counts["inside"] is None
    assert snapshot.counts["entered"] is None
    assert snapshot.counts["throughput"] is None


def test_live_people_fast_read_does_not_touch_database_or_systemd(tmp_path):
    app, _ = service(tmp_path)
    app.service_manager.status = lambda: pytest.fail("Live poll must not invoke systemd")
    app._database_counts = lambda config: pytest.fail("Live poll must not query SQLite")
    assert app.live_people().total is None
