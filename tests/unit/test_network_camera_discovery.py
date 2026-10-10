from __future__ import annotations

import ipaddress
import json
import subprocess

import pytest

from visitor_counter import network_camera_discovery as discovery


def test_reolink_url_and_credentials_escaping() -> None:
    assert discovery.reolink_rtsp_url("192.168.20.11") == (
        "rtsp://192.168.20.11:554/Preview_01_sub"
    )
    assert discovery.reolink_rtsp_url(
        "192.168.20.11", "admin", "sp@ce:word", stream="main"
    ) == "rtsp://admin:sp%40ce%3Aword@192.168.20.11:554/Preview_01_main"


@pytest.mark.parametrize("network", ["8.8.8.0/24", "10.0.0.0/16", "::1/128", "garbage"])
def test_scan_rejects_invalid_or_untrusted_targets(network: str) -> None:
    with pytest.raises(ValueError):
        discovery.scan_rtsp_network(network)


def test_scan_uses_explicit_network_and_only_reports_open_rtsp(monkeypatch) -> None:
    calls = []

    def fake_probe(host: str, timeout: float, ports: tuple[int, ...]):
        calls.append(host)
        return discovery.RtspCandidate(host, 554) if host == "192.168.50.2" else None

    monkeypatch.setattr(discovery, "_probe", fake_probe)
    result = discovery.scan_rtsp_network("192.168.50.0/30", max_workers=1)
    assert result == [discovery.RtspCandidate("192.168.50.2", 554)]
    assert sorted(calls) == ["192.168.50.1", "192.168.50.2"]


def test_interface_scopes_are_limited_to_nearest_24(monkeypatch) -> None:
    class Completed:
        returncode = 0
        stdout = json.dumps([{
            "ifname": "eth0",
            "addr_info": [{"family": "inet", "local": "192.168.22.16", "prefixlen": 16}],
        }, {
            "ifname": "docker0",
            "addr_info": [{"family": "inet", "local": "172.17.0.1", "prefixlen": 16}],
        }])

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Completed())
    assert discovery.local_networks() == [ipaddress.IPv4Network("192.168.22.0/24")]


def test_missing_ip_utility_is_not_fatal(monkeypatch) -> None:
    def missing(*args, **kwargs):
        raise FileNotFoundError("ip")

    monkeypatch.setattr(subprocess, "run", missing)
    assert discovery.local_networks() == []


@pytest.mark.parametrize("host", ["1.2.3.4", "not-an-ip", "127.0.0.1"])
def test_invalid_reolink_host_rejected(host: str) -> None:
    with pytest.raises(ValueError):
        discovery.reolink_rtsp_url(host)


def test_partial_credentials_not_silently_dropped() -> None:
    with pytest.raises(ValueError, match="Benutzername"):
        discovery.reolink_rtsp_url("10.0.0.8", username="admin")


def test_visible_lan_neighbors_are_not_claimed_as_video(monkeypatch) -> None:
    class Response:
        returncode = 0
        stdout = json.dumps([
            {"dst": "192.168.50.7", "state": ["REACHABLE"]},
            {"dst": "192.168.50.8", "state": "FAILED"},
            {"dst": "192.168.51.9", "state": "STALE"},
        ])

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Response())
    assert discovery.neighbor_lan_hosts("192.168.50.0/24") == ["192.168.50.7"]
    monkeypatch.setattr(discovery, "scan_rtsp_network", lambda cidr="": [])
    monkeypatch.setattr(discovery, "discover_onvif_hosts", lambda: [])
    found = discovery.discover_network_cameras("192.168.50.0/24")
    assert [item.host for item in found] == ["192.168.50.7"]
    assert found[0].discovery_method == "LAN"
    assert not found[0].rtsp_ready
    assert "unbestätigt" in found[0].label
