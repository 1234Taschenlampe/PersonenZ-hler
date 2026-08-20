from __future__ import annotations

import os
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

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppConfig:
        try:
            return load_config(self.path)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise SettingsError(
                f"Konfiguration konnte nicht geöffnet werden: {exc}"
            ) from exc

    def save(self, config: AppConfig) -> None:
        errors = validate_config(config)
        if errors:
            raise SettingsError(
                "Konfiguration ist ungültig:\n"
                + "\n".join(f"• {item}" for item in errors)
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = yaml.safe_dump(asdict(config), sort_keys=False, allow_unicode=True)
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
