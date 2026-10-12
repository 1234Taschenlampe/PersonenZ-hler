from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
from time import time
from urllib.parse import unquote, urlsplit

import pytest

from scripts import status_api
from scripts.configure_preferred_display import preferred_profile
from visitor_counter import camera_address_recovery as recovery
from visitor_counter import network_readiness as network
from visitor_counter.camera_manager import CameraCredentialError, camera_source_with_credentials
from visitor_counter.configuration import AppConfig, CameraConfig
from visitor_counter.runtime_paths import RuntimePaths


def test_api_reads_pipeline_xdg_status_not_database_parent(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONENZAEHLER_USE_XDG", "1")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    data = tmp_path / "xdg/personenzaehler"
    data.mkdir(parents=True)
    config = AppConfig()
    config.database.path = str(tmp_path / "different-db/counts.sqlite3")
    expected = {"timestamp": time(), "counts": {"inside": 7}}
    (data / "live_status.json").write_text(json.dumps(expected))
    assert status_api._read_live_status(tmp_path, config) == expected
    expected["timestamp"] -= 11
    (data / "live_status.json").write_text(json.dumps(expected))
    assert status_api._read_live_status(tmp_path, config) is None


def test_explicit_paths_win_over_xdg_and_local_license_key_is_preserved(tmp_path):
    config = tmp_path / "private/config.yaml"
    config.parent.mkdir()
    key = config.parent / "license_public_key.pem"
    key.write_text("public test fixture")
    env = {"PERSONENZAEHLER_USE_XDG": "1", "PERSONENZAEHLER_CONFIG_FILE": str(config),
           "PERSONENZAEHLER_DATA_DIR": str(tmp_path / "data-override")}
    paths = RuntimePaths.discover(tmp_path, environ=env, home=tmp_path)
    assert paths.config_file == config
    assert paths.data_dir == tmp_path / "data-override"
    assert paths.license_public_key == key
    env["PERSONENZAEHLER_LICENSE_PUBLIC_KEY"] = str(tmp_path / "other-key")
    assert RuntimePaths.discover(tmp_path, environ=env).license_public_key == tmp_path / "other-key"


def test_network_wait_retries_dhcp_and_has_exact_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(network.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(network.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(network, "address_available", lambda host: clock[0] >= 1)
    assert network.wait_for_address("api-host", timeout=2)
    assert clock[0] == 1
    monkeypatch.setattr(network, "address_available", lambda host: False)
    assert not network.wait_for_address("api-host", timeout=0.7)
    assert clock[0] == pytest.approx(1.7)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_network_availability_supports_local_ipv4_ipv6(host):
    if host == "::1" and not socket.has_ipv6:
        pytest.skip("No IPv6")
    assert network.address_available(host)


def test_camera_environment_credentials_roundtrip_and_never_leak():
    cfg = CameraConfig("camera_1", username_env="CAM_USER", password_env="CAM_PASS")
    raw = "rtsp://[2001:db8::1]:8554/profile?x=1"
    source = camera_source_with_credentials(raw, cfg, {"CAM_USER": "test@user", "CAM_PASS": "fake:/pass"})
    parsed = urlsplit(source)
    assert unquote(parsed.username) == "test@user"
    assert unquote(parsed.password) == "fake:/pass"
    assert parsed.hostname == "2001:db8::1" and parsed.port == 8554
    with pytest.raises(CameraCredentialError) as caught:
        camera_source_with_credentials(raw, cfg, {"CAM_USER": "test@user"})
    assert "test@user" not in str(caught.value)
    assert camera_source_with_credentials(source, cfg, {}) == source


def test_probe_hosts_are_bounded_direct_private_networks_only():
    interfaces = [{"addr_info": [{"local": "192.168.77.2", "prefixlen": 30},
                                  {"local": "10.2.3.4", "prefixlen": 8},
                                  {"local": "203.0.113.4", "prefixlen": 30},
                                  {"local": "::1", "prefixlen": 128}]}]
    assert recovery.attached_hosts(interfaces) == {"192.168.77.1", "192.168.77.2"}


def test_recovery_requires_unique_mac_and_preserves_port_credentials_and_profile():
    cfg = {"cameras": {"camera_1": {"device": "rtsp://fake:example@192.168.77.1:8554/profile?x=1"}}}
    pins = {"camera_1": "02:00:00:00:00:01"}
    neighbours = [{"dst": "192.168.77.2", "lladdr": pins["camera_1"], "state": ["REACHABLE"]}]
    new = recovery.recovered_sources(cfg, pins, neighbours, {("192.168.77.2", 8554)})
    assert new["camera_1"] == "rtsp://fake:example@192.168.77.2:8554/profile?x=1"
    assert not recovery.recovered_sources(cfg, pins, neighbours, {("192.168.77.2", 554)})
    neighbours.append({"dst": "192.168.77.3", "lladdr": pins["camera_1"]})
    assert not recovery.recovered_sources(cfg, pins, neighbours, {("192.168.77.2", 8554), ("192.168.77.3", 8554)})
    assert not recovery.recovered_sources(cfg, pins, neighbours, {("192.168.77.1", 8554)})


def test_recovery_preserves_concurrent_configuration_edits(tmp_path):
    path = tmp_path / "config.yaml"
    old = b"original: true\n"
    path.write_bytes(b"newer: true\n")
    assert not recovery.replace_if_unchanged(path, old, {"original": False})
    assert path.read_bytes() == b"newer: true\n"
    assert not list(tmp_path.glob(".camera-address-*"))


def test_no_pins_means_no_network_or_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "_ip_json", lambda *a: pytest.fail("network scan without pins"))
    assert recovery.recover(tmp_path / "missing-config", tmp_path / "missing-pins", apply=True) == 0


def test_preferred_display_uses_actual_monitor_and_refuses_ambiguous_outputs():
    output = {"name": "DP-2", "enabled": True, "modes": [{"width": 1600, "height": 900, "refresh": 59.94, "preferred": True}]}
    assert "DP-2 enable mode 1600x900@59.940000Hz" in preferred_profile([output])
    with pytest.raises(ValueError):
        preferred_profile([output, dict(output, name="HDMI-A-2")])


@pytest.mark.skipif(sys.platform != "linux", reason="Local desktop session requires bash")
def test_desktop_session_rejects_ssh_without_importing_environment(tmp_path):
    import os
    env = dict(os.environ, SSH_CONNECTION="test", DISPLAY=":10")
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(["bash", str(root / "scripts/desktop_session.sh")], env=env, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "local desktop" in proc.stdout
