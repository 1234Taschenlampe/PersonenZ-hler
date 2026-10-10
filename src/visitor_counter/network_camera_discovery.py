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
from time import monotonic
from urllib.parse import quote
from uuid import uuid4


# Restrict discovery to RFC 1918 LAN addresses, not every special IPv4 range
# that Python classifies as is_private (e.g. documentation/loopback blocks).
LAN_RANGES = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


def _is_lan(value: ipaddress.IPv4Address | ipaddress.IPv4Network) -> bool:
    return any(value in scope if isinstance(value, ipaddress.IPv4Address)
               else value.subnet_of(scope) for scope in LAN_RANGES)


@dataclass(frozen=True, order=True)
class RtspCandidate:
    host: str
    port: int
    discovery_method: str = "RTSP"
    rtsp_ready: bool = True

    @property
    def label(self) -> str:
        return (
            f"{self.host}:{self.port} · RTSP-Port erreichbar"
            if self.rtsp_ready
            else (
                f"{self.host} · ONVIF gefunden, RTSP noch unbestätigt"
                if self.discovery_method == "ONVIF"
                else f"{self.host} · LAN-Gerät sichtbar; Kamerafunktion unbestätigt"
            )
        )

    @property
    def url_template(self) -> str:
        return f"rtsp://{self.host}:{self.port}/Preview_01_sub"


def _allowed_network(value: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError("Ungültiges Netz: Bitte IPv4/CIDR verwenden, z. B. 192.168.1.0/24.") from exc
    if not isinstance(network, ipaddress.IPv4Network) or not _is_lan(network):
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
                if not _is_lan(ip):
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
    cidr: str = "", *, timeout: float = 0.7, max_workers: int = 48,
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


def discover_onvif_hosts(*, timeout: float = 1.4) -> list[str]:
    """Bounded ONVIF WS-Discovery multicast; never sends camera credentials.

    ONVIF discovery identifies possible IP cameras even if the RTSP port is
    disabled. A discovery response is NOT proof that a video feed is available.
    """
    if not 0 < timeout <= 3:
        raise ValueError("ONVIF-Timeout außerhalb des erlaubten Bereichs.")
    packet = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
        f'<e:Header><w:MessageID>uuid:{uuid4()}</w:MessageID>'
        '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action e:mustUnderstand="true">'
        'http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
        '</e:Header><e:Body><d:Probe/></e:Body></e:Envelope>'
    ).encode("utf-8")
    hosts: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.settimeout(min(0.3, timeout))
            sock.sendto(packet, ("239.255.255.250", 3702))
            deadline = monotonic() + timeout
            while monotonic() < deadline:
                sock.settimeout(min(0.25, max(0.01, deadline - monotonic())))
                try:
                    data, address = sock.recvfrom(32768)
                except socket.timeout:
                    continue
                if b"ProbeMatches" not in data and b"ProbeMatch" not in data:
                    continue
                try:
                    ip = ipaddress.IPv4Address(address[0])
                except ValueError:
                    continue
                if _is_lan(ip):
                    hosts.add(str(ip))
    except OSError:
        return []
    return sorted(hosts, key=lambda host: int(ipaddress.IPv4Address(host)))[:64]


def neighbor_lan_hosts(cidr: str = "") -> list[str]:
    """Read already-visible local IPv4 neighbours without active probing."""
    networks = [_allowed_network(cidr)] if cidr.strip() else local_networks()
    if not networks:
        return []
    try:
        response = subprocess.run(
            ["ip", "-j", "-4", "neigh", "show"],
            capture_output=True, text=True, check=False, timeout=3,
        )
        rows = json.loads(response.stdout) if response.returncode == 0 else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    hosts: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("state", "")).upper() in {"FAILED", "INCOMPLETE", "NOARP"}:
            continue
        try:
            address = ipaddress.IPv4Address(str(row["dst"]))
        except (KeyError, ValueError):
            continue
        if _is_lan(address) and any(address in subnet for subnet in networks):
            hosts.add(str(address))
    return sorted(hosts, key=lambda host: int(ipaddress.IPv4Address(host)))[:64]


def discover_network_cameras(cidr: str = "") -> list[RtspCandidate]:
    """Find RTSP-ready devices and ONVIF candidates, deduplicated by IP.

    For explicit CIDR only that network is scanned; multicast responses are
    accepted only if inside it. No discovery step guarantees video access.
    """
    scope = _allowed_network(cidr) if cidr.strip() else None
    rtsp = scan_rtsp_network(cidr)
    by_ip = {device.host: device for device in rtsp}
    for host in discover_onvif_hosts():
        ip = ipaddress.IPv4Address(host)
        if scope is not None and ip not in scope:
            continue
        if host not in by_ip:
            by_ip[host] = RtspCandidate(host, 554, "ONVIF", False)
    # The neighbour table can reveal devices even when RTSP/ONVIF are disabled.
    # They are clearly labelled as unverified LAN devices, never as video-ready.
    for host in neighbor_lan_hosts(cidr):
        by_ip.setdefault(host, RtspCandidate(host, 554, "LAN", False))
    return sorted(by_ip.values(), key=lambda item: int(ipaddress.IPv4Address(item.host)))


def reolink_rtsp_url(
    host: str, username: str = "", password: str = "", *,
    port: int = 554, stream: str = "sub",
) -> str:
    """Create a Reolink RTSP URL without silently interpreting an IP as USB."""
    try:
        ip = ipaddress.IPv4Address(host.strip())
    except ValueError as exc:
        raise ValueError("Bitte eine gültige IPv4-Adresse der Kamera eingeben.") from exc
    if not _is_lan(ip):
        raise ValueError("Die Kamera muss eine private, routbare IPv4-Adresse haben.")
    if not 1 <= port <= 65535:
        raise ValueError("Ungültiger Port.")
    if stream not in {"main", "sub"}:
        raise ValueError("Stream muss 'main' oder 'sub' sein.")
    if bool(username) != bool(password):
        raise ValueError("Benutzername und Passwort müssen gemeinsam eingegeben werden.")
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    return f"rtsp://{auth}{ip}:{port}/Preview_01_{stream}"
