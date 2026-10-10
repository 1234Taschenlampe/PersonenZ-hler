"""Local-only unpixelated previews and edge counting secure defaults."""
from __future__ import annotations

from pathlib import Path

import pytest

from visitor_counter.configuration import AppConfig, validate_config
from visitor_counter.video_stream import LocalPreviewExporter, FrameStreamExporter


def test_fresh_config_enables_exit_edge_without_enabling_remote_video() -> None:
    config = AppConfig()
    assert config.display.anonymization_mode == "none"
    assert not config.display.show_camera_preview
    assert not config.privacy.video_stream_enabled
    assert all(camera.counting_mode == "exit_edge" for camera in config.cameras.values())
    assert not validate_config(config)


def test_local_raw_preview_optin_passes_configuration_checks() -> None:
    config = AppConfig()
    config.display.show_camera_preview = True
    assert not validate_config(config)


def test_raw_frames_remain_forbidden_on_remote_video() -> None:
    config = AppConfig()
    config.privacy.video_stream_enabled = True
    errors = validate_config(config)
    assert any("Remote video requires full-frame anonymization" in error for error in errors)


def test_local_raw_preview_fails_closed_outside_linux_ram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "visitor_counter.video_stream.local_preview_directory",
        lambda _root: tmp_path / "preview",
    )
    with pytest.raises(ValueError, match="RAM-backed"):
        LocalPreviewExporter(tmp_path, enabled=True, anonymization_mode="none")


def test_remote_exporter_never_allows_unmasked_stream(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="without anonymization"):
        FrameStreamExporter(tmp_path, enabled=True, anonymization_mode="none")
