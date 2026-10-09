from __future__ import annotations

import json
from pathlib import Path
from time import time

import scripts.status_api as status_api
from visitor_counter.application_service import ApplicationService
from visitor_counter.configuration import AppConfig
from visitor_counter.runtime_paths import RuntimePaths
from visitor_counter.settings_service import SettingsService


def test_source_config_stores_xdg_database_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PERSONENZAEHLER_USE_XDG", "1")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data-home"))
    settings = SettingsService(tmp_path / "config-home" / "personenzaehler" / "config.yaml")
    settings.save(AppConfig())
    expected = tmp_path / "data-home" / "personenzaehler" / "person_counter.sqlite3"
    assert Path(settings.load().database.path) == expected


def test_mobile_api_sees_live_status_from_xdg_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PERSONENZAEHLER_DATA_DIR", raising=False)
    config = AppConfig()
    config.database.path = str(tmp_path / "xdg" / "personenzaehler" / "person_counter.sqlite3")
    live_file = Path(config.database.path).parent / "live_status.json"
    live_file.parent.mkdir(parents=True)
    live_file.write_text(json.dumps({"timestamp": time(), "counts": {"inside": 3}}))
    assert status_api._read_live_status(tmp_path, config)["counts"]["inside"] == 3


def test_source_gui_controls_user_counter_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PERSONENZAEHLER_USE_XDG", "1")
    paths = RuntimePaths.discover(tmp_path, home=tmp_path, environ={"PERSONENZAEHLER_USE_XDG": "1"})
    manager = ApplicationService(paths).service_manager
    assert manager.unit == "personenzaehler.service"
    assert manager.user_service is True
