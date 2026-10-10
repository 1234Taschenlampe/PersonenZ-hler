from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from visitor_counter.configuration import AppConfig, save_config
from scripts.service_preflight import ready

ROOT = Path(__file__).resolve().parents[2]


def test_unconfigured_pi_service_skips_without_starting(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config = AppConfig()
    save_config(config, config_file)
    ok, detail = ready(tmp_path, config_file)
    assert not ok
    assert "Kamera" in detail


def test_configured_pipeline_prerequisites_allow_service(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://camera-1.local/stream"
    config.cameras["camera_2"].device = "rtsp://camera-2.local/stream"
    files = (
        config.model.hef_path,
        config.model.reid_hef_path,
        config.model.postprocess_onnx_path,
        config.model.postprocess_config_path,
    )
    for filename in files:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder for readiness test only")
    save_config(config, config_file)
    ok, detail = ready(tmp_path, config_file)
    assert ok, detail
    assert "Dateivoraussetzungen" in detail
    (tmp_path / config.model.hef_path).unlink()
    ok, detail = ready(tmp_path, config_file)
    assert not ok
    assert "fehlt" in detail


def test_model_requirements_skip_training_and_torch() -> None:
    text = "\n".join(line for line in (ROOT / "requirements-pi.txt").read_text(encoding="utf-8").lower().splitlines() if not line.lstrip().startswith("#"))
    assert "-e ." in text
    assert "onnxruntime" in text
    assert "ultralytics" not in text
    assert "torch" not in text


def test_preflight_accepts_one_camera_with_detection_disabled(tmp_path: Path) -> None:
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://camera-1.local/stream"
    config.cameras["camera_2"].device = None
    config.model.detector_enabled = False
    config_file = tmp_path / "config.yaml"
    save_config(config, config_file)
    ok, detail = ready(tmp_path, config_file)
    assert ok, detail


def test_preflight_accepts_one_camera_with_detector_models(tmp_path: Path) -> None:
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://camera-1.local/stream"
    config.cameras["camera_2"].device = None
    config.model.reid_required = False
    for filename in (
        config.model.hef_path,
        config.model.postprocess_onnx_path,
        config.model.postprocess_config_path,
    ):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"readiness fixture")
    config_file = tmp_path / "config.yaml"
    save_config(config, config_file)
    ok, detail = ready(tmp_path, config_file)
    assert ok, detail
    (tmp_path / config.model.hef_path).unlink()
    assert not ready(tmp_path, config_file)[0]


@pytest.mark.skipif(sys.platform != "linux" or os.geteuid() == 0, reason="Linux unprivileged runner")
def test_installer_dry_run_is_non_mutating(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "install_linux_app.sh"), "--dry-run"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "DRY-RUN" in proc.stdout
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / ".cache").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux systemd unit tests")
def test_service_units_do_not_reload_without_changes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home.mkdir()
    config = home / ".config" / "personenzaehler"
    config.mkdir(parents=True)
    (config / "config.yaml").write_text("cameras: {}\n")
    (config / "api.env").write_text("# fixture\n")
    log = tmp_path / "systemctl.log"
    tool = bin_dir / "systemctl"
    tool.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >> "$MOCK_LOG"\n'
        'if [[ "$2" == "show-environment" ]]; then exit 0; fi\n'
        'if [[ "$2" == "is-enabled" || "$2" == "is-active" ]]; then exit 0; fi\n'
        "exit 0\n"
    )
    tool.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "MOCK_LOG": str(log),
        "PATH": str(bin_dir) + os.pathsep + env["PATH"],
        "PERSONENZAEHLER_USE_XDG": "1",
    })
    script = str(ROOT / "scripts" / "install_autostart.sh")
    first_restart_count = 0
    for attempt in (1, 2):
        result = subprocess.run(
            ["bash", script], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        recorded = log.read_text().splitlines()
        if attempt == 1:
            assert sum("daemon-reload" in line for line in recorded) == 1
            first_restart_count = sum("restart personenzaehler" in line for line in recorded)
        else:
            assert sum("daemon-reload" in line for line in recorded) == 1
            assert sum("restart personenzaehler" in line for line in recorded) == first_restart_count
            assert "daemon-reload übersprungen" in result.stdout
    unit = (home / ".config/systemd/user/personenzaehler.service").read_text()
    assert "ExecCondition=" in unit


@pytest.mark.skipif(sys.platform != "linux", reason="bash is required")
def test_install_scripts_bash_syntax() -> None:
    for script in ["quick_install.sh", "install_linux_app.sh", "install_autostart.sh", "install_desktop_icon.sh"]:
        result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / script)])
        assert result.returncode == 0, script
