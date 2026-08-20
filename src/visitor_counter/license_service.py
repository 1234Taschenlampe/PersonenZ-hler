from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .license_guard import (
    LicenseError,
    _load_public_key,
    _validate_claims,
    _verify_document,
    machine_fingerprint,
)
from .runtime_paths import RuntimePaths


@dataclass(frozen=True)
class LicenseStatus:
    valid: bool
    label: str
    detail: str
    license_id: str = ""
    fingerprint: str = ""


class LicenseService:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths

    def inspect(self) -> LicenseStatus:
        fingerprint = machine_fingerprint()
        if not self.paths.license_file.exists():
            return LicenseStatus(
                False,
                "Lizenz nicht vorhanden",
                "Importieren Sie eine signierte Lizenzdatei.",
                fingerprint=fingerprint,
            )
        if not self.paths.license_public_key.exists():
            return LicenseStatus(
                False,
                "Lizenzprüfung nicht bereit",
                "Der öffentliche Lizenzschlüssel fehlt.",
                fingerprint=fingerprint,
            )
        try:
            key = _load_public_key(self.paths.license_public_key)
            document = _verify_document(self.paths.license_file.read_bytes(), key)
            license_id = _validate_claims(document, fingerprint)
        except (OSError, LicenseError) as exc:
            return LicenseStatus(
                False, "Lizenz ungültig", str(exc), fingerprint=fingerprint
            )
        return LicenseStatus(
            True,
            "Lizenz gültig",
            "Signatur und lokale Lizenzansprüche sind gültig.",
            license_id,
            fingerprint,
        )

    def import_file(self, source: Path) -> LicenseStatus:
        if not source.is_file():
            raise LicenseError("Die ausgewählte Lizenzdatei existiert nicht")
        raw = source.read_bytes()
        if len(raw) > 256_000:
            raise LicenseError("Die Lizenzdatei ist ungewöhnlich groß")
        key = _load_public_key(self.paths.license_public_key)
        document = _verify_document(raw, key)
        _validate_claims(document, machine_fingerprint())
        if self.paths.system_layout:
            self._install_privileged(raw)
            return self.inspect()
        self.paths.license_file.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            handle, name = tempfile.mkstemp(
                prefix=".license.", suffix=".tmp", dir=self.paths.license_file.parent
            )
            temporary = Path(name)
            with open(handle, "wb", closefd=True) as stream:
                stream.write(raw)
                stream.flush()
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            temporary.replace(self.paths.license_file)
        except OSError as exc:
            raise LicenseError(
                f"Lizenz konnte nicht installiert werden: {exc}"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return self.inspect()

    def _install_privileged(self, raw: bytes) -> None:
        helper = Path("/usr/lib/personenzaehler/personenzaehler-admin")
        if os.name != "posix" or shutil.which("pkexec") is None or not helper.exists():
            raise LicenseError("Die grafische Systemberechtigung ist nicht installiert")
        handle, name = tempfile.mkstemp(
            prefix="personenzaehler-license-", suffix=".json"
        )
        temporary = Path(name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            result = subprocess.run(
                ["pkexec", str(helper), "install-license", str(temporary.resolve())],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise LicenseError(detail or "Lizenz konnte nicht installiert werden")
        except OSError as exc:
            raise LicenseError(
                f"Lizenz konnte nicht installiert werden: {exc}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
