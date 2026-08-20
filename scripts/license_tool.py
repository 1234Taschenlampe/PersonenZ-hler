from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _canonical(document: dict) -> bytes:
    unsigned = {key: value for key, value in document.items() if key != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def generate_keypair(private_path: Path, public_path: Path) -> None:
    if private_path.exists() or public_path.exists():
        raise SystemExit("Refusing to overwrite an existing key file")
    private = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_path.chmod(0o600)
    print(f"Private key: {private_path}")
    print(f"Public key:  {public_path}")
    print("Keep the private key OFF the Raspberry Pi and OUT of Git.")


def sign_document(input_path: Path, private_path: Path, output_path: Path) -> None:
    private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise SystemExit("Private key must be Ed25519")
    document = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit("License document must be a JSON object")
    document["signature"] = base64.b64encode(private.sign(_canonical(document))).decode("ascii")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Signed: {output_path}")


def template(path: Path, license_id: str, fingerprint: str | None) -> None:
    document = {
        "product": "PersonenZ-hler",
        "license_id": license_id,
        "enabled": True,
        "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "expires_at": None,
        "machine_fingerprints": [fingerprint] if fingerprint else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Template: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PersonenZ-hler license administration")
    sub = parser.add_subparsers(dest="command", required=True)

    keys = sub.add_parser("generate-keys")
    keys.add_argument("--private", type=Path, required=True)
    keys.add_argument("--public", type=Path, required=True)

    tmpl = sub.add_parser("template")
    tmpl.add_argument("--out", type=Path, required=True)
    tmpl.add_argument("--license-id", required=True)
    tmpl.add_argument("--fingerprint")

    sign = sub.add_parser("sign")
    sign.add_argument("--in", dest="input", type=Path, required=True)
    sign.add_argument("--private", type=Path, required=True)
    sign.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "generate-keys":
        generate_keypair(args.private, args.public)
    elif args.command == "template":
        template(args.out, args.license_id, args.fingerprint)
    elif args.command == "sign":
        sign_document(args.input, args.private, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
