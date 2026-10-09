from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from dataclasses import dataclass
from pathlib import Path

from .runtime_paths import RuntimePaths


class ModelInstallationError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstalledModel:
    kind: str
    path: Path
    size_bytes: int


class ModelInstallationService:
    TARGETS = {
        "detector": "yolo26m_detection_hailo10h_640.hef",
        "reid": "osnet_x1_0_hailo10h.hef",
    }
    OFFICIAL_MANIFESTS = {
        "detector": ("yolo26m_detection_hailo10h_manifest.json", "hef_source_url"),
        "reid": ("osnet_x1_0_hailo10h_manifest.json", "source_url"),
    }
    TRUSTED_HOST = "hailo-model-zoo.s3.eu-west-2.amazonaws.com"
    MAX_HEF_BYTES = 2_000_000_000

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        admin_helper: Path = Path("/usr/lib/personenzaehler/personenzaehler-admin"),
    ) -> None:
        self.paths = paths
        self.admin_helper = admin_helper

    def install(self, kind: str, source: Path) -> InstalledModel:
        if kind not in self.TARGETS:
            raise ModelInstallationError("Unbekannter Modelltyp")
        source = source.expanduser()
        if (
            source.is_symlink()
            or not source.is_file()
            or source.suffix.lower() != ".hef"
        ):
            raise ModelInstallationError(
                "Es muss eine reguläre Hailo-HEF-Datei ausgewählt werden"
            )
        size = source.stat().st_size
        if size < 1024 or size > 2_000_000_000:
            raise ModelInstallationError("Die HEF-Dateigröße ist unplausibel")
        target = self.paths.model_dir / self.TARGETS[kind]
        if self.paths.system_layout:
            if (
                os.name != "posix"
                or shutil.which("pkexec") is None
                or not self.admin_helper.exists()
            ):
                raise ModelInstallationError(
                    "Die grafische Systemberechtigung ist nicht installiert"
                )
            result = subprocess.run(
                [
                    "pkexec",
                    str(self.admin_helper),
                    "install-model",
                    kind,
                    str(source.resolve()),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise ModelInstallationError(detail or "Modellimport fehlgeschlagen")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary: Path | None = None
            try:
                handle, name = tempfile.mkstemp(
                    prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
                )
                temporary = Path(name)
                with (
                    os.fdopen(handle, "wb") as destination,
                    source.open("rb") as origin,
                ):
                    shutil.copyfileobj(origin, destination, length=1024 * 1024)
                    destination.flush()
                    os.fsync(destination.fileno())
                temporary.chmod(0o640)
                temporary.replace(target)
            except OSError as exc:
                raise ModelInstallationError(
                    f"Modell konnte nicht installiert werden: {exc}"
                ) from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return InstalledModel(kind, target, size)
 
    def _official_source(self, kind: str) -> tuple[str, str]:
        """Pin Hailo's exact official release URL to the repository SHA-256."""
        if kind not in self.TARGETS:
            raise ModelInstallationError("Unbekannter Modelltyp")
        name, url_field = self.OFFICIAL_MANIFESTS[kind]
        path = self.paths.project_root / "models" / "manifests" / name
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            url = str(manifest[url_field])
            expected = str(manifest["hef_sha256"]).lower()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ModelInstallationError(
                f"Offizielles Modellmanifest fehlt oder ist ungültig: {path}"
            ) from exc
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != self.TRUSTED_HOST
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or not parsed.path.startswith("/ModelZoo/Compiled/v")
            or "/hailo10h/" not in parsed.path
            or not parsed.path.endswith(".hef")
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
        ):
            raise ModelInstallationError("Unsichere oder unvollständige Hailo-Modellquelle")
        return url, expected

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def download_official(self, kind: str, *, timeout: float = 30.0) -> InstalledModel:
        """Download official, hash-pinned HEF; refuse unexpected content.

        Files are obtained from Hailo directly, not redistributed via GitHub.
        Installation of the file is not proof that HailoRT can execute it.
        """
        url, expected_sha = self._official_source(kind)
        target = self.paths.model_dir / self.TARGETS[kind]
        if target.exists() or target.is_symlink():
            if (
                not target.is_symlink() and target.is_file()
                and 1024 <= target.stat().st_size <= self.MAX_HEF_BYTES
                and self._digest(target) == expected_sha
            ):
                return InstalledModel(kind, target, target.stat().st_size)
            raise ModelInstallationError(
                f"Vorhandene HEF ist nicht die freigegebene Originaldatei: {target}. "
                "Es wurde nichts überschrieben. Bitte separat sichern und prüfen."
            )
        if timeout <= 0 or timeout > 120:
            raise ModelInstallationError("Download-Timeout ist ungültig")
        with tempfile.TemporaryDirectory(prefix="personenzaehler-model-") as temp_dir:
            temporary = Path(temp_dir) / f"{kind}.hef"
            digest = hashlib.sha256()
            total = 0
            request = Request(
                url, headers={"User-Agent": "Personenzaehler-Official-Model-Installer/1"}
            )
            try:
                with urlopen(request, timeout=timeout) as response:
                    final_url = urlsplit(response.geturl())
                    if (
                        final_url.scheme != "https"
                        or final_url.hostname != self.TRUSTED_HOST
                    ):
                        raise ModelInstallationError(
                            "Weiterleitung auf einen fremden Download-Host verweigert"
                        )
                    with temporary.open("wb") as handle:
                        while block := response.read(1024 * 1024):
                            total += len(block)
                            if total > self.MAX_HEF_BYTES:
                                raise ModelInstallationError("HEF ist ungewöhnlich groß")
                            digest.update(block)
                            handle.write(block)
                        handle.flush()
                        os.fsync(handle.fileno())
            except (OSError, TimeoutError) as exc:
                raise ModelInstallationError(
                    f"Offizieller Hailo-Download fehlgeschlagen: {exc}"
                ) from exc
            if total < 1024 or digest.hexdigest() != expected_sha:
                raise ModelInstallationError(
                    f"SHA-256-Prüfung fehlgeschlagen für {kind}. "
                    "Datei wird nicht installiert. Prüfe Hersteller-Release und Manifest."
                )
            # The existing install method handles both unprivileged XDG paths
            # and protected Debian package installations via the policy helper.
            result = self.install(kind, temporary)
            if self._digest(result.path) != expected_sha:
                raise ModelInstallationError(
                    "Prüfsumme nach Modellinstallation ist nicht korrekt"
                )
            return result
