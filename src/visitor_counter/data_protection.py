from __future__ import annotations

from base64 import urlsafe_b64decode
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .configuration import DatabaseConfig


class DataProtectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataProtector:
    """Encrypt sensitive SQLite fields and create keyed, unlinkable integer IDs."""

    _fernet: Fernet
    _hmac_key: bytes

    @classmethod
    def from_key(cls, encoded_key: str) -> "DataProtector":
        value = encoded_key.strip().encode("ascii")
        try:
            raw = urlsafe_b64decode(value)
        except Exception as exc:  # noqa: BLE001
            raise DataProtectionError("The data key is not valid URL-safe base64.") from exc
        if len(raw) != 32:
            raise DataProtectionError("The data key must be a Fernet-compatible 32-byte key.")
        return cls(Fernet(value), hashlib.sha256(raw + b"visitor-counter-id-v1").digest())

    def encrypt_text(self, value: str | None) -> str | None:
        if value is None or value.startswith("enc:v1:"):
            return value
        token = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
        return f"enc:v1:{token}"

    def decrypt_text(self, value: str | None) -> str | None:
        if value is None or not value.startswith("enc:v1:"):
            return value
        try:
            return self._fernet.decrypt(value.removeprefix("enc:v1:").encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise DataProtectionError("Stored data cannot be decrypted with the configured key.") from exc

    def pseudonymize_id(self, scope: str, value: int | None) -> int | None:
        if value is None:
            return None
        digest = hmac.new(self._hmac_key, f"{scope}:{value}".encode("ascii"), hashlib.sha256).digest()
        return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)

    def pseudonymize_text(self, scope: str, value: str | None) -> str | None:
        if value is None or value.startswith("hmac:v1:"):
            return value
        digest = hmac.new(self._hmac_key, f"{scope}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac:v1:{digest}"

    def encrypt_bytes(self, value: bytes) -> bytes:
        return self._fernet.encrypt(value)


def load_data_protector(config: DatabaseConfig, project_root: Path) -> DataProtector | None:
    encoded = os.environ.get(config.encryption_key_env, "").strip() if config.encryption_key_env else ""
    if not encoded and config.encryption_key_file:
        key_path = Path(config.encryption_key_file).expanduser()
        if not key_path.is_absolute():
            key_path = project_root / key_path
        key_path = key_path.resolve()
        if key_path.is_symlink() or not key_path.is_file():
            raise DataProtectionError(f"Data key file is not a regular file: {key_path}")
        if os.name == "posix" and key_path.stat().st_mode & 0o077:
            raise DataProtectionError(f"Data key file permissions must be 0600: {key_path}")
        encoded = key_path.read_text(encoding="ascii").strip()
    if not encoded:
        if config.store_events and config.encryption_required:
            raise DataProtectionError(
                f"Event storage is enabled but {config.encryption_key_env or 'a data encryption key'} is missing."
            )
        return None
    return DataProtector.from_key(encoded)
