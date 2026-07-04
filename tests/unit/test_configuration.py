from __future__ import annotations

from pathlib import Path

from visitor_counter.configuration import AppConfig, load_config, save_config, validate_config


def test_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    config = AppConfig()
    config.model.confidence_threshold = 0.42
    save_config(config, path)
    loaded = load_config(path)
    assert loaded.model.confidence_threshold == 0.42
    assert validate_config(loaded) == []


def test_config_validation_rejects_bad_confidence() -> None:
    config = AppConfig()
    config.model.confidence_threshold = 2.0
    assert validate_config(config)


def test_config_validation_rejects_detector_fallback() -> None:
    config = AppConfig()
    config.model.hef_path = "models/yolo11x_hailo10h.hef"
    config.model.detector_fallback_enabled = True
    errors = validate_config(config)
    assert any("fallback" in error.lower() for error in errors)
    assert any("yolo26x_person_hailo10h_640.hef" in error for error in errors)
