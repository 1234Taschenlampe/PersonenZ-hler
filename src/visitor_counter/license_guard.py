from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_PRODUCT_ID = "PersonenZ-hler"
_ALLOWED_GITHUB_HOSTS = {"github.com", "api.github.com", "raw.githubusercontent.com"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class LicenseError(RuntimeError):
    pass


@dataclass(frozen=True)
class LicenseDecision:
    allowed: bool
    reason: str
    license_id: str = ""
    machine_fingerprint: str = ""
    online_checked: bool = False


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise LicenseError(f"{name} enthält keinen gültigen booleschen Wert")


def _canonical_payload(data: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in data.items() if key != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _read_machine_id() -> str:
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return socket.gethostname()


def machine_fingerprint() -> str:
    """Return a one-way device fingerprint for optional license binding."""
    raw = f"{_PRODUCT_ID}|{_read_machine_id()}".encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _load_public_key(path: Path) -> Ed25519PublicKey:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LicenseError(f"Lizenz-Public-Key fehlt: {path}") from exc
    try:
        key = serialization.load_pem_public_key(raw)
    except (TypeError, ValueError) as exc:
        raise LicenseError("Lizenz-Public-Key ist ungültig") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise LicenseError("Für die Lizenzprüfung wird ein Ed25519-Public-Key benötigt")
    return key


def _verify_document(raw: bytes, public_key: Ed25519PublicKey) -> dict[str, Any]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseError("Lizenzdokument ist kein gültiges JSON") from exc
    if not isinstance(document, dict):
        raise LicenseError("Lizenzdokument muss ein JSON-Objekt sein")
    signature_text = document.get("signature")
    if not isinstance(signature_text, str) or not signature_text:
        raise LicenseError("Lizenzsignatur fehlt")
    try:
        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(signature, _canonical_payload(document))
    except Exception as exc:
        raise LicenseError("Lizenzsignatur ist ungültig") from exc
    return document


def _parse_expiry(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise LicenseError("expires_at muss eine ISO-8601-Zeitangabe sein")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LicenseError("expires_at ist ungültig") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_claims(document: dict[str, Any], fingerprint: str) -> str:
    if document.get("product") != _PRODUCT_ID:
        raise LicenseError("Lizenz gehört nicht zu diesem Produkt")
    license_id = str(document.get("license_id", "")).strip()
    if not license_id:
        raise LicenseError("license_id fehlt")
    if document.get("enabled") is not True:
        raise LicenseError("Lizenz wurde deaktiviert")
    expiry = _parse_expiry(document.get("expires_at"))
    if expiry is not None and datetime.now(timezone.utc) >= expiry:
        raise LicenseError("Lizenz ist abgelaufen")
    machines = document.get("machine_fingerprints", [])
    if machines is None:
        machines = []
    if not isinstance(machines, list) or not all(isinstance(item, str) for item in machines):
        raise LicenseError("machine_fingerprints ist ungültig")
    if machines and fingerprint not in machines:
        raise LicenseError("Lizenz ist nicht für dieses Gerät freigeschaltet")
    return license_id


def _fetch_online_document(url: str, timeout_seconds: float) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _ALLOWED_GITHUB_HOSTS:
        raise LicenseError("Online-Lizenzcheck ist nur über HTTPS zu GitHub erlaubt")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PersonenZ-hler-License/1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - host/scheme are allow-listed above
            return response.read(256_000)
    except HTTPError as exc:
        if exc.code == 404:
            raise LicenseError("Online-Freischaltung wurde nicht gefunden") from exc
        raise LicenseError(f"GitHub-Lizenzcheck fehlgeschlagen (HTTP {exc.code})") from exc
    except (URLError, OSError) as exc:
        raise LicenseError("GitHub-Lizenzcheck ist nicht erreichbar") from exc


def evaluate_license(project_root: Path) -> LicenseDecision:
    """Validate local signed license and, by default, a matching GitHub entitlement.

    Production defaults are fail-closed. Development can explicitly opt out with
    VISITOR_COUNTER_LICENSE_REQUIRED=0. The online requirement can only be
    disabled explicitly with VISITOR_COUNTER_LICENSE_ONLINE_REQUIRED=0.
    """
    required = _env_bool("VISITOR_COUNTER_LICENSE_REQUIRED", True)
    fingerprint = machine_fingerprint()
    if not required:
        return LicenseDecision(True, "Lizenzprüfung wurde explizit für Entwicklung deaktiviert", machine_fingerprint=fingerprint)

    license_path = project_root / os.environ.get("VISITOR_COUNTER_LICENSE_FILE", "config/license.json")
    public_key_path = project_root / os.environ.get("VISITOR_COUNTER_LICENSE_PUBLIC_KEY", "config/license_public_key.pem")
    public_key = _load_public_key(public_key_path)
    try:
        local_raw = license_path.read_bytes()
    except OSError as exc:
        raise LicenseError(f"Lokale Lizenzdatei fehlt: {license_path}") from exc
    local = _verify_document(local_raw, public_key)
    license_id = _validate_claims(local, fingerprint)

    online_required = _env_bool("VISITOR_COUNTER_LICENSE_ONLINE_REQUIRED", True)
    online_url = os.environ.get("VISITOR_COUNTER_LICENSE_URL", "").strip()
    if not online_url:
        if online_required:
            raise LicenseError("GitHub-Freischalt-URL fehlt")
        return LicenseDecision(True, "Signierte lokale Lizenz ist gültig", license_id, fingerprint, False)

    try:
        timeout = max(1.0, min(float(os.environ.get("VISITOR_COUNTER_LICENSE_TIMEOUT", "5")), 30.0))
    except ValueError:
        timeout = 5.0
    remote_raw = _fetch_online_document(online_url, timeout)
    remote = _verify_document(remote_raw, public_key)
    remote_id = _validate_claims(remote, fingerprint)
    if remote_id != license_id:
        raise LicenseError("Online-Freischaltung gehört zu einer anderen Lizenz")
    return LicenseDecision(True, "Lokale Lizenz und GitHub-Freischaltung sind gültig", license_id, fingerprint, True)


def enforce_license(project_root: Path) -> LicenseDecision:
    decision = evaluate_license(project_root)
    if not decision.allowed:
        raise LicenseError(decision.reason)
    return decision


if __name__ == "__main__":
    print(machine_fingerprint())
