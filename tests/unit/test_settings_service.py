from pathlib import Path

import pytest

from visitor_counter.configuration import AppConfig
from visitor_counter.settings_service import SettingsError, SettingsService


def test_settings_service_saves_atomically_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config" / "config.yaml"
    service = SettingsService(path)
    config = AppConfig()
    config.privacy.controller_name = "Beispiel GmbH"
    service.save(config)
    assert service.load().privacy.controller_name == "Beispiel GmbH"
    assert not list(path.parent.glob("*.tmp"))


def test_settings_service_rejects_unsafe_remote_api(tmp_path: Path) -> None:
    service = SettingsService(tmp_path / "config.yaml")
    config = AppConfig()
    config.api.bind_host = "0.0.0.0"
    with pytest.raises(SettingsError, match="TLS"):
        service.save(config)


def test_settings_service_updates_known_dotted_fields(tmp_path: Path) -> None:
    service = SettingsService(tmp_path / "config.yaml")
    service.save(AppConfig())
    result = service.update({"database.retention_hours": 48, "api.port": 9000})
    assert result.database.retention_hours == 48
    assert result.api.port == 9000
