from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from visitor_counter.license_guard import LicenseError, _canonical_payload, _validate_claims, _verify_document


def _signed_document(private: Ed25519PrivateKey, *, enabled: bool = True, machines: list[str] | None = None) -> bytes:
    document = {
        "product": "PersonenZ-hler",
        "license_id": "test-license",
        "enabled": enabled,
        "expires_at": None,
        "machine_fingerprints": machines or [],
    }
    document["signature"] = base64.b64encode(private.sign(_canonical_payload(document))).decode("ascii")
    return json.dumps(document).encode("utf-8")


def test_valid_signed_document_is_accepted() -> None:
    private = Ed25519PrivateKey.generate()
    document = _verify_document(_signed_document(private), private.public_key())
    assert _validate_claims(document, "sha256:test") == "test-license"


def test_tampered_document_is_rejected() -> None:
    private = Ed25519PrivateKey.generate()
    document = json.loads(_signed_document(private).decode("utf-8"))
    document["enabled"] = False
    with pytest.raises(LicenseError):
        _verify_document(json.dumps(document).encode("utf-8"), private.public_key())


def test_disabled_license_is_rejected() -> None:
    private = Ed25519PrivateKey.generate()
    document = _verify_document(_signed_document(private, enabled=False), private.public_key())
    with pytest.raises(LicenseError):
        _validate_claims(document, "sha256:test")


def test_wrong_machine_is_rejected() -> None:
    private = Ed25519PrivateKey.generate()
    document = _verify_document(_signed_document(private, machines=["sha256:other"]), private.public_key())
    with pytest.raises(LicenseError):
        _validate_claims(document, "sha256:this-device")
