"""Bounded LAN discovery for RTSP cameras, intended for explicit user action.

Only IPv4 private networks directly attached to the host, or a user supplied
private CIDR of at most 256 addresses, may be scanned. A reachable RTSP port
is a candidate, not proof that the device is an authenticated video camera.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import ipaddress
import json
import socket
import subprocess
from urllib.parse import quote


@dataclass(frozen=True, order=True)
class RtspCandidate:
    host: str
    port: int

    @property
    def label(self) -> str:
        return f"RTSP-Gerät {self.host}:{self.port} (Zugangsdaten erforderlich)"

    @property
    def url_template(self) -> str:
        return f"rtsp://{self.host}:{self.port}/Preview_01_sub"


def _allowed_network(value: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError("Ungültiges Netz: Bitte IPv4/CIDR verwenden, z. B. 192.168.1.0/24.") from exc
    if not isinstance(network, ipaddress.IPv4Network) or not network.is_private:
        raise ValueError("Nur private IPv4-Netze dürfen durchsucht werden.")
    if network.prefixlen < 24:
        raise ValueError("Netz zu groß: Maximal ein /24-Netz (254 Hosts) pro Suche.")
    return network


def local_networks() -> list[ipaddress.IPv4Network]:
    """Use local interface addresses, never guess the user's router subnet."""
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "address", "show", "scope", "global"],
            capture_output=True, text=True, check=False, timeout=3,
        )
        interfaces = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []

    networks: set[ipaddress.IPv4Network] = set()
    for iface in interfaces:
        name = str(iface.get("ifname", ""))
        if name.startswith(("docker", "veth", "br-", "virbr", "tailscale", "tun")):
            continue
        for address in iface.get("addr_info", []):
            if address.get("family") != "inet":
                continue
            try:
                ip = ipaddress.IPv4Address(address["local"])
                if not ip.is_private or ip.is_loopback or ip.is_link_local:
                    continue
                prefix = max(24, int(address.get("prefixlen", 24)))
                networks.add(_allowed_network(f"{ip}/{prefix}"))
            except (ValueError, KeyError, TypeError):
                continue
    return sorted(networks, key=lambda n: int(n.network_address))[:4]


def _probe(host: str, timeout: float, ports: tuple[int, ...]) -> RtspCandidate | None:
    for port in ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return RtspCandidate(host, port)
        except (OSError, TimeoutError):
            continue
    return None


def scan_rtsp_network(
    cidr: str = "", *, timeout: float = 0.25, max_workers: int = 32,
    ports: tuple[int, ...] = (554, 8554),
) -> list[RtspCandidate]:
    """Explicit, bounded LAN TCP discovery. No passwords and no video sent."""
    networks = [_allowed_network(cidr)] if cidr.strip() else local_networks()
    if not 0 < timeout <= 3:
        raise ValueError("Timeout außerhalb des erlaubten Bereichs.")
    if not 1 <= max_workers <= 64:
        raise ValueError("max_workers außerhalb des erlaubten Bereichs.")
    if not ports or any(not 1 <= p <= 65535 for p in ports):
        raise ValueError("Ungültiger RTSP-Port.")
    hosts = sorted({str(host) for network in networks for host in network.hosts()},
                   key=lambda host: int(ipaddress.IPv4Address(host)))
    if not hosts:
        return []
    found: list[RtspCandidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_probe, host, timeout, ports) for host in hosts]
        for future in as_completed(futures):
            candidate = future.result()
            if candidate:
                found.append(candidate)
    return sorted(found, key=lambda item: (int(ipaddress.IPv4Address(item.host)), item.port))


def reolink_rtsp_url(
    host: str, username: str = "", password: str = "", *,
    port: int = 554, stream: str = "sub",
) -> str:
    """Create a Reolink RTSP URL without silently interpreting an IP as USB."""
    try:
        ip = ipaddress.IPv4Address(host.strip())
    except ValueError as exc:
        raise ValueError("Bitte eine gültige IPv4-Adresse der Kamera eingeben.") from exc
    if not ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_link_local:
        raise ValueError("Die Kamera muss eine private, routbare IPv4-Adresse haben.")
    if not 1 <= port <= 65535:
        raise ValueError("Ungültiger Port.")
    if stream not in {"main", "sub"}:
        raise ValueError("Stream muss 'main' oder 'sub' sein.")
    if bool(username) != bool(password):
        raise ValueError("Benutzername und Passwort müssen gemeinsam eingegeben werden.")
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    return f"rtsp://{auth}{ip}:{port}/Preview_01_{stream}"
