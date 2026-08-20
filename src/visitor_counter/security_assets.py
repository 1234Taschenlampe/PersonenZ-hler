from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

from .configuration import AppConfig
from .runtime_paths import RuntimePaths


class SecurityAssetError(RuntimeError):
    pass


class SecurityAssetService:
    TARGETS = {
        "certificate": ("tls.crt", {".crt", ".pem"}, 0o644),
        "private_key": ("tls.key", {".key", ".pem"}, 0o600),
    }

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        admin_helper: Path = Path("/usr/lib/personenzaehler/personenzaehler-admin"),
    ) -> None:
        self.paths = paths
        self.admin_helper = admin_helper

    def install_tls_asset(self, kind: str, source: Path) -> Path:
        target_spec = self.TARGETS.get(kind)
        if target_spec is None:
            raise SecurityAssetError("Unbekannter TLS-Dateityp")
        filename, suffixes, mode = target_spec
        source = source.expanduser()
        if (
            source.is_symlink()
            or not source.is_file()
            or source.suffix.lower() not in suffixes
        ):
            raise SecurityAssetError(
                "Es muss eine reguläre PEM-/TLS-Datei ausgewählt werden"
            )
        size = source.stat().st_size
        if size < 32 or size > 1_000_000:
            raise SecurityAssetError("Die TLS-Dateigröße ist unplausibel")
        target = (
            Path("/etc/personenzaehler") / filename
            if self.paths.system_layout
            else self.paths.config_file.parent / filename
        )
        if self.paths.system_layout:
            self._run_helper(f"install-tls-{kind.replace('_', '-')}", source)
        else:
            self._copy_atomic(source, target, mode)
        return target

    def export_pairing(self, config: AppConfig, destination: Path) -> Path:
        if not config.api.enabled:
            raise SecurityAssetError("Die API ist deaktiviert")
        if config.api.bind_host in {"127.0.0.1", "::1", "localhost"}:
            raise SecurityAssetError(
                "Für Android muss in den Einstellungen eine TLS-geschützte Netzwerkbindung aktiviert werden"
            )
        token = self._viewer_token(config)
        if len(token) < config.api.minimum_token_length:
            raise SecurityAssetError("Der Viewer-Token fehlt oder ist zu kurz")
        host = config.api.bind_host
        if host in {"0.0.0.0", "::"}:
            host = self._local_address()
        certificate = Path(config.api.tls_certificate).expanduser()
        fingerprint = ""
        if certificate.is_file():
            fingerprint = hashlib.sha256(certificate.read_bytes()).hexdigest()
        payload = {
            "format": "personenzaehler-pairing-v1",
            "base_url": f"https://{host}:{config.api.port}",
            "viewer_token": token,
            "tls_certificate_sha256": fingerprint,
        }
        destination = destination.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.chmod(0o600)
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise SecurityAssetError(
                f"Pairing-Datei konnte nicht gespeichert werden: {exc}"
            ) from exc
        return destination

    def _viewer_token(self, config: AppConfig) -> str:
        if self.paths.system_layout:
            result = self._run_helper("read-viewer-token")
            return result.stdout.strip()
        direct = os.environ.get(config.api.viewer_token_env, "").strip()
        if direct:
            return direct
        env_path = self.paths.config_file.parent / "api.env"
        if env_path.is_file():
            prefix = f"{config.api.viewer_token_env}="
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith(prefix):
                    return line.removeprefix(prefix).strip()
        return ""

    def _run_helper(
        self, action: str, source: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        if (
            os.name != "posix"
            or shutil.which("pkexec") is None
            or not self.admin_helper.exists()
        ):
            raise SecurityAssetError(
                "Die grafische Systemberechtigung ist nicht installiert"
            )
        command = ["pkexec", str(self.admin_helper), action]
        if source is not None:
            command.append(str(source.resolve()))
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise SecurityAssetError(
                detail or "Sicherheitsdatei konnte nicht verarbeitet werden"
            )
        return result

    @staticmethod
    def _copy_atomic(source: Path, target: Path, mode: int) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(name)
        try:
            with (
                os.fdopen(handle, "wb") as destination,
                source.open("rb") as origin,
            ):
                shutil.copyfileobj(origin, destination)
                destination.flush()
                os.fsync(destination.fileno())
            temporary.chmod(mode)
            temporary.replace(target)
        except OSError as exc:
            raise SecurityAssetError(
                f"TLS-Datei konnte nicht installiert werden: {exc}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _local_address() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                connection.connect(("192.0.2.1", 9))
                return str(connection.getsockname()[0])
        except OSError:
            return socket.gethostname()
