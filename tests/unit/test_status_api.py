from __future__ import annotations

from pathlib import Path

import scripts.status_api as status_api
from visitor_counter.configuration import AppConfig, save_config


def test_status_api_reports_detector_and_reid_without_secrets(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "data").mkdir()
    save_config(AppConfig(), tmp_path / "config" / "config.yaml")

    status = status_api.build_status(tmp_path)

    assert status["service"] == "visitor-counter"
    assert "detector" in status
    assert "reid" in status
    serialized = str(status).lower()
    assert "password" not in serialized
    assert "token" not in serialized
    assert "embedding" not in serialized
