"""Opt-in DHCP recovery by operator-pinned MAC; never guess credentials/devices.

Only directly attached RFC1918 IPv4 networks are probed. No source is changed
unless exactly one reachable neighbour matches the pinned physical address.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

import yaml

PRIVATE = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def attached_hosts(interfaces: list[dict], limit: int = 4096) -> set[str]:
    hosts: set[str] = set()
    for interface in interfaces:
        for info in interface.get("addr_info", []):
            try:
                network = ipaddress.ip_network(f"{info['local']}/{info['prefixlen']}", strict=False)
            except (ValueError, KeyError):
                continue
            if network.version != 4 or not any(network.subnet_of(n) for n in PRIVATE):
                continue
            if network.num_addresses > limit:
                continue
            candidates = {str(ip) for ip in network.hosts()}
            if len(hosts | candidates) <= limit:
                hosts.update(candidates)
    return hosts


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def recovered_sources(config: dict, pins: dict[str, str], neighbours: list[dict],
                      endpoints: set[tuple[str, int]]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for camera_id, mac in pins.items():
        if not isinstance(mac, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac):
            raise ValueError("Invalid pinned camera MAC")
        camera = config.get("cameras", {}).get(camera_id, {})
        old = urlsplit(camera.get("device") or "")
        if old.scheme.lower() not in {"rtsp", "rtsps"} or not old.hostname:
            continue
        port = old.port or (322 if old.scheme.lower() == "rtsps" else 554)
        if (old.hostname, port) in endpoints:
            continue
        candidates = {n.get("dst") for n in neighbours
                      if n.get("lladdr", "").lower() == mac.lower()
                      and (n.get("dst"), port) in endpoints
                      and n.get("state") not in (["FAILED"], ["INCOMPLETE"])}
        if len(candidates) != 1:
            continue
        host = candidates.pop()
        userinfo = old.netloc.rsplit("@", 1)[0] + "@" if "@" in old.netloc else ""
        updates[camera_id] = urlunsplit((old.scheme, f"{userinfo}{host}:{port}", old.path, old.query, old.fragment))
    return updates


def replace_if_unchanged(path: Path, original: bytes, config: dict) -> bool:
    if path.is_symlink():
        raise ValueError("Symlink configuration refused")
    handle, name = tempfile.mkstemp(prefix=".camera-address-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            yaml.safe_dump(config, output, sort_keys=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        if path.read_bytes() != original:
            return False
        temporary.replace(path)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _ip_json(*args: str) -> list[dict]:
    result = subprocess.run(["ip", "-j", *args], check=True, capture_output=True, text=True, timeout=10)
    return json.loads(result.stdout)


def recover(config_file: Path, pins_file: Path, *, apply: bool = False) -> int:
    if not pins_file.is_file():
        print("Camera DHCP recovery disabled: no operator-pinned devices")
        return 0
    if config_file.is_symlink() or pins_file.is_symlink():
        raise ValueError("Symlink configuration refused")
    original = config_file.read_bytes()
    config = yaml.safe_load(original)
    pins = json.loads(pins_file.read_text(encoding="utf-8"))
    if not isinstance(pins, dict):
        raise ValueError("Camera pins must be a camera-ID to MAC mapping")
    # Validate pins before performing any network operation.
    recovered_sources(config, pins, [], set())
    sources = [urlsplit(config.get("cameras", {}).get(cid, {}).get("device") or "") for cid in pins]
    ports = {s.port or (322 if s.scheme.lower() == "rtsps" else 554) for s in sources if s.scheme.lower() in {"rtsp", "rtsps"}}
    endpoints = {(s.hostname, s.port or (322 if s.scheme.lower() == "rtsps" else 554)) for s in sources
                 if s.hostname and s.scheme.lower() in {"rtsp", "rtsps"} and reachable(s.hostname, s.port or (322 if s.scheme.lower() == "rtsps" else 554))}
    if all(not s.hostname or (s.hostname, s.port or (322 if s.scheme.lower() == "rtsps" else 554)) in endpoints for s in sources):
        print("Configured camera addresses reachable; no changes")
        return 0
    hosts = attached_hosts(_ip_json("-4", "address"))
    with ThreadPoolExecutor(max_workers=64) as pool:
        for port in ports:
            endpoints.update((h, port) for h, ok in zip(sorted(hosts), pool.map(lambda h: reachable(h, port), sorted(hosts))) if ok)
    updates = recovered_sources(config, pins, _ip_json("neigh"), endpoints)
    # Output camera IDs only, never credentials, addresses or MACs.
    print(json.dumps({"recoverable_camera_ids": sorted(updates), "apply": apply}))
    if not updates or not apply:
        return 0
    for cid, source in updates.items():
        config["cameras"][cid]["device"] = source
    if not replace_if_unchanged(config_file, original, config):
        print("Configuration changed concurrently; next timer run will retry")
        return 0
    subprocess.run(["systemctl", "--user", "try-restart", "personenzaehler.service"], check=True, timeout=40)
    return len(updates)
