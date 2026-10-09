from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .configuration import AppConfig, load_config, validate_config


class SettingsError(RuntimeError):
    pass


class SettingsService:
    """Validate and atomically persist the user-visible configuration."""

    def __init__(
        self,
        path: Path,
        *,
        allow_privileged: bool = False,
        admin_helper: Path = Path("/usr/lib/personenzaehler/personenzaehler-admin"),
    ) -> None:
        self.path = path
        self.allow_privileged = allow_privileged
        self.admin_helper = admin_helper

    def load(self) -> AppConfig:
        try:
            return load_config(self.path)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise SettingsError(
                f"Konfiguration konnte nicht geöffnet werden: {exc}"
            ) from exc

    def save(self, config: AppConfig) -> None:
        # The Pi source installer keeps mutable data outside its Git checkout.
        # The production pipeline uses config.database.path directly, therefore
        # persist the absolute XDG location once instead of splitting state
        # between project_root/data and the GUI's XDG_DATA_HOME.
        if (
            not self.allow_privileged
            and os.environ.get("PERSONENZAEHLER_USE_XDG", "").lower()
            in {"1", "true", "yes"}
            and not Path(config.database.path).expanduser().is_absolute()
        ):
            base = Path(
                os.environ.get(
                    "XDG_DATA_HOME", str(Path.home() / ".local" / "share")
                )
            ).expanduser()
            config.database.path = str(
                base / "personenzaehler" / Path(config.database.path).name
            )
        errors = validate_config(config)
        if errors:
            raise SettingsError(
                "Konfiguration ist ungültig:\n"
                + "\n".join(f"• {item}" for item in errors)
            )
        payload = yaml.safe_dump(asdict(config), sort_keys=False, allow_unicode=True)
        if self.allow_privileged:
            self._save_privileged(payload)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            handle, name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            temporary = Path(name)
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            temporary.replace(self.path)
        except OSError as exc:
            raise SettingsError(
                f"Konfiguration konnte nicht gespeichert werden: {exc}"
            ) from exc
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)

    def _save_privileged(self, payload: str) -> None:
        if (
            os.name != "posix"
            or shutil.which("pkexec") is None
            or not self.admin_helper.exists()
        ):
            raise SettingsError(
                "Die grafische Systemberechtigung ist nicht installiert"
            )
        handle, name = tempfile.mkstemp(
            prefix="personenzaehler-config-", suffix=".yaml"
        )
        temporary = Path(name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            result = subprocess.run(
                [
                    "pkexec",
                    str(self.admin_helper),
                    "install-config",
                    str(temporary.resolve()),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise SettingsError(
                    detail or "Konfiguration konnte nicht installiert werden"
                )
        except OSError as exc:
            raise SettingsError(
                f"Konfiguration konnte nicht gespeichert werden: {exc}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def update(self, values: dict[str, Any]) -> AppConfig:
        """Apply dotted field names such as ``privacy.controller_name``."""
        config = self.load()
        for dotted, value in values.items():
            parts = dotted.split(".")
            target: Any = config
            for part in parts[:-1]:
                if not hasattr(target, part):
                    raise SettingsError(f"Unbekannte Einstellung: {dotted}")
                target = getattr(target, part)
            field = parts[-1]
            if not hasattr(target, field):
                raise SettingsError(f"Unbekannte Einstellung: {dotted}")
            setattr(target, field, value)
        self.save(config)
        return config
