from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _xdg_path(env: dict[str, str], name: str, fallback: Path) -> Path:
    value = env.get(name, "").strip()
    return Path(value).expanduser() if value else fallback


@dataclass(frozen=True)
class RuntimePaths:
    """Single source of truth for development and installed filesystem paths."""

    project_root: Path
    config_file: Path
    data_dir: Path
    log_dir: Path
    cache_dir: Path
    model_dir: Path
    license_file: Path
    license_public_key: Path
    state_dir: Path
    system_layout: bool = False

    @property
    def first_run_marker(self) -> Path:
        return self.state_dir / "first-run-complete.json"

    @property
    def live_status_file(self) -> Path:
        return self.data_dir / "live_status.json"

    @classmethod
    def discover(
        cls,
        project_root: Path | None = None,
        *,
        system_layout: bool = False,
        environ: dict[str, str] | None = None,
        home: Path | None = None,
    ) -> "RuntimePaths":
        env = dict(os.environ if environ is None else environ)
        root = (
            Path(project_root or env.get("PERSONENZAEHLER_PROJECT_ROOT", Path.cwd()))
            .expanduser()
            .resolve()
        )
        user_home = Path(home or Path.home()).expanduser()
        config_home = _xdg_path(env, "XDG_CONFIG_HOME", user_home / ".config")
        data_home = _xdg_path(env, "XDG_DATA_HOME", user_home / ".local" / "share")
        state_home = _xdg_path(env, "XDG_STATE_HOME", user_home / ".local" / "state")
        cache_home = _xdg_path(env, "XDG_CACHE_HOME", user_home / ".cache")

        if system_layout:
            config_file = Path(
                env.get(
                    "PERSONENZAEHLER_CONFIG_FILE", "/etc/personenzaehler/config.yaml"
                )
            )
            data_dir = Path(
                env.get("PERSONENZAEHLER_DATA_DIR", "/var/lib/personenzaehler")
            )
            log_dir = Path(
                env.get("PERSONENZAEHLER_LOG_DIR", "/var/log/personenzaehler")
            )
            cache_dir = Path(
                env.get("PERSONENZAEHLER_CACHE_DIR", "/var/cache/personenzaehler")
            )
            model_dir = Path(
                env.get("PERSONENZAEHLER_MODEL_DIR", "/var/lib/personenzaehler/models")
            )
            license_file = Path(
                env.get(
                    "PERSONENZAEHLER_LICENSE_FILE", "/etc/personenzaehler/license.json"
                )
            )
            public_key = Path(
                env.get(
                    "PERSONENZAEHLER_LICENSE_PUBLIC_KEY",
                    "/usr/share/personenzaehler/license_public_key.pem",
                )
            )
        else:
            config_file = Path(
                env.get(
                    "PERSONENZAEHLER_CONFIG_FILE", str(root / "config" / "config.yaml")
                )
            )
            data_dir = Path(env.get("PERSONENZAEHLER_DATA_DIR", str(root / "data")))
            log_dir = Path(env.get("PERSONENZAEHLER_LOG_DIR", str(root / "logs")))
            cache_dir = Path(env.get("PERSONENZAEHLER_CACHE_DIR", str(root / "cache")))
            model_dir = Path(env.get("PERSONENZAEHLER_MODEL_DIR", str(root / "models")))
            license_file = Path(
                env.get(
                    "PERSONENZAEHLER_LICENSE_FILE",
                    str(root / "config" / "license.json"),
                )
            )
            public_key = Path(
                env.get(
                    "PERSONENZAEHLER_LICENSE_PUBLIC_KEY",
                    str(root / "config" / "license_public_key.pem"),
                )
            )

        state_dir = Path(
            env.get("PERSONENZAEHLER_STATE_DIR", str(state_home / "personenzaehler"))
        )
        if not system_layout and env.get("PERSONENZAEHLER_USE_XDG", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            config_file = config_home / "personenzaehler" / "config.yaml"
            data_dir = data_home / "personenzaehler"
            log_dir = state_dir / "log"
            cache_dir = cache_home / "personenzaehler"
            license_file = config_home / "personenzaehler" / "license.json"

        return cls(
            project_root=root,
            config_file=config_file.expanduser(),
            data_dir=data_dir.expanduser(),
            log_dir=log_dir.expanduser(),
            cache_dir=cache_dir.expanduser(),
            model_dir=model_dir.expanduser(),
            license_file=license_file.expanduser(),
            license_public_key=public_key.expanduser(),
            state_dir=state_dir.expanduser(),
            system_layout=system_layout,
        )

    def ensure_user_directories(self) -> None:
        """Create only locations expected to be writable by the current user."""
        for path in (self.state_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)
            try:
                path.chmod(0o700)
            except OSError:
                pass
        if not self.system_layout:
            for path in (self.data_dir, self.log_dir):
                path.mkdir(parents=True, exist_ok=True)
