from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
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
