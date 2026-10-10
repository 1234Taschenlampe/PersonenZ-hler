"""Bounded RTSP access diagnostics; successful DESCRIBE is not video proof."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
import socket
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit


@dataclass(frozen=True)
class RTSPAccess:
    port_reachable: bool
    authentication: str
    sdp_available: bool
    detail: str


def _response(connection: socket.socket, request: str) -> tuple[int, str]:
    connection.sendall(request.encode("utf-8"))
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 16384:
        chunk = connection.recv(4096)
        if not chunk:
            break
        data += chunk
    headers = data.split(b"\r\n\r\n", 1)[0].decode("utf-8", errors="replace")
    body_size = len(data.split(b"\r\n\r\n", 1)[1]) if b"\r\n\r\n" in data else 0
    length = re.search(r"^Content-Length:\s*(\d+)", headers, re.I | re.M)
    if length:
        remaining = int(length[1]) - body_size
        if remaining > 65536:
            raise ValueError("Response too large")
        while remaining > 0:
            chunk = connection.recv(min(4096, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
    match = re.match(r"RTSP/\d\.\d\s+(\d{3})", headers)
    return (int(match[1]) if match else 0), headers


def _quoted(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise ValueError("Invalid header characters")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _authorization(headers: str, user: str, password: str, uri: str) -> str:
    challenge = re.search(r"^WWW-Authenticate:\s*(.*)$", headers, re.I | re.M)
    if not challenge:
        return ""
    value = challenge[1].strip()
    if value.lower().startswith("basic"):
        return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    if not value.lower().startswith("digest"):
        return ""
    fields = {
        key.lower(): quoted or raw
        for key, quoted, raw in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', value)
    }
    nonce = fields.get("nonce", "")
    if not nonce or fields.get("algorithm", "MD5").upper() != "MD5":
        return ""
    def digest(text: str) -> str:
        # MD5 is required by the camera's RTSP Digest authentication protocol.
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
    ha1 = digest(f"{user}:{fields.get('realm', '')}:{password}")
    ha2 = digest("DESCRIBE:" + uri)
    extras = ""
    qop = fields.get("qop", "")
    if qop:
        if "auth" not in [part.strip() for part in qop.split(",")]:
            return ""
        cnonce = secrets.token_hex(8)
        response = digest(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}")
        extras = f", qop=auth, nc=00000001, cnonce={_quoted(cnonce)}"
    else:
        response = digest(f"{ha1}:{nonce}:{ha2}")
    if "opaque" in fields:
        extras += ", opaque=" + _quoted(fields["opaque"])
    return (
        f"Digest username={_quoted(user)}, realm={_quoted(fields.get('realm', ''))}, "
        f"nonce={_quoted(nonce)}, uri={_quoted(uri)}, response={_quoted(response)}{extras}"
    )


def probe_rtsp_source(source: str, *, timeout: float = 2.0) -> RTSPAccess:
    reachable = False
    try:
        parts = urlsplit(source)
        if parts.scheme.lower() != "rtsp" or not parts.hostname:
            return RTSPAccess(False, "unknown", False, "RTSP-Diagnose für diese Quelle nicht verfügbar")
        port = parts.port or 554
        host = parts.hostname
        netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        uri = urlunsplit(("rtsp", netloc, parts.path or "/", parts.query, ""))
        if any(ord(char) < 32 for char in uri):
            raise ValueError("Invalid request characters")
        with socket.create_connection((host, port), timeout=timeout) as connection:
            reachable = True
            connection.settimeout(timeout)
            request = f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: {{sequence}}\r\nAccept: application/sdp\r\n{{auth}}\r\n"
            code, headers = _response(connection, request.format(sequence=1, auth=""))
            authentication = "not_required"
            if code == 401:
                if parts.username is None:
                    return RTSPAccess(True, "required", False, "RTSP-Port erreichbar; Anmeldung erforderlich (401)")
                authorization = _authorization(headers, unquote(parts.username), unquote(parts.password or ""), uri)
                if not authorization:
                    return RTSPAccess(True, "unknown", False, "RTSP-Port erreichbar; Anmeldeverfahren nicht unterstützt")
                code, _ = _response(connection, request.format(sequence=2, auth="Authorization: " + authorization + "\r\n"))
                authentication = "authenticated" if code == 200 else "unknown"
            if code in {401, 403}:
                return RTSPAccess(True, "rejected", False, f"RTSP-Port erreichbar; Anmeldung abgelehnt ({code})")
            if code == 200:
                auth_detail = "Anmeldung erfolgreich" if authentication == "authenticated" else "keine Anmeldung angefordert"
                return RTSPAccess(True, authentication, True, f"RTSP-Port erreichbar; {auth_detail}; Streamprofil erreichbar, Videoframes noch unbestätigt")
            return RTSPAccess(True, authentication, False, f"RTSP-Port erreichbar; Streamprofil nicht verfügbar (RTSP {code})")
    except (OSError, ValueError):
        detail = "RTSP-Port erreichbar; Protokollantwort fehlt oder ungültig" if reachable else "RTSP-Port nicht erreichbar; IP, Route und Kamera-RTSP prüfen"
        return RTSPAccess(reachable, "unknown", False, detail)
