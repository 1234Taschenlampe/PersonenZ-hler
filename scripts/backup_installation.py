#!/usr/bin/env python3
"""Private, consistent backup without stopping or modifying running services.

Output contains secrets/databases and MUST remain outside Git. SQLite backup()
includes committed WAL data. Restoration of code/services must never rewind the
live databases; inspect the manifest and select an explicitly tested checkout.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visitor_counter.configuration import load_config  # noqa: E402
from visitor_counter.runtime_paths import RuntimePaths  # noqa: E402


def backup_database(source: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Quote filesystem paths correctly, including spaces, # and ? characters.
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as original:
        with sqlite3.connect(target) as copy:
            original.backup(copy)
            integrity = copy.execute("PRAGMA integrity_check").fetchone()[0]
    target.chmod(0o600)
    if integrity != "ok":
        raise ValueError("Backup SQLite integrity check failed")
    return {"name": target.name, "integrity": integrity,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def private_copy(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise ValueError("Symlink in private backup source refused")
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        for child in source.iterdir():
            private_copy(child, target / child.name)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, target)
        target.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path, action="append", default=[])
    args = parser.parse_args()
    paths = RuntimePaths.discover(args.project_root)
    destination = args.output.expanduser().resolve()
    for protected in (paths.project_root, paths.config_file.parent, paths.data_dir, paths.state_dir):
        if destination == protected.resolve() or protected.resolve() in destination.parents:
            raise ValueError("Backup must be outside source and runtime directories")
    if destination.exists():
        raise FileExistsError("Backup destination already exists")
    os.umask(0o077)
    destination.mkdir(parents=True, mode=0o700)
    config = load_config(paths.config_file)
    configured = Path(config.database.path).expanduser()
    configured = configured if configured.is_absolute() else paths.project_root / configured
    databases = list(dict.fromkeys([configured, configured.parent / "daily_unique.sqlite3", *args.database]))
    if len({p.name for p in databases}) != len(databases):
        raise ValueError("Database backup names must be unique")
    manifest = {"created": datetime.now(timezone.utc).isoformat(), "databases": [],
                "warning": "PRIVATE: contains credentials and operational data; never commit or upload"}
    for source in databases:
        if source.exists():
            manifest["databases"].append(backup_database(source, destination / "databases" / source.name))
    private_copy(paths.config_file.parent, destination / "configuration")
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    units = config_home / "systemd/user"
    if units.exists():
        for p in units.iterdir():
            if (p.name.startswith("personenzaehler") or p.name.startswith("visitor-counter")) and not p.is_symlink():
                private_copy(p, destination / "user-units" / p.name)
    for relative in ("autostart/personenzaehler.desktop", "kanshi/config"):
        source = config_home / relative
        if source.exists():
            private_copy(source, destination / "desktop" / relative)
    commit = subprocess.check_output(["git", "-C", str(paths.project_root), "rev-parse", "HEAD"], text=True).strip()
    manifest["commit"] = commit
    manifest["dirty"] = bool(subprocess.check_output(["git", "-C", str(paths.project_root), "status", "--porcelain"], text=True).strip())
    # Retain uncommitted SOURCE changes as a private binary Git patch too.
    patch = subprocess.check_output(["git", "-C", str(paths.project_root), "diff", "--binary", "HEAD"])
    (destination / "local-tracked-changes.patch").write_bytes(patch)
    subprocess.run(["git", "-C", str(paths.project_root), "archive", "--format=tar.gz", "-o", str(destination / "source.tar.gz"), commit], check=True)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Private SQLite/configuration/service/source backup completed; services unchanged.")
    print(f"Commit: {commit}; databases: {len(manifest['databases'])}; tracked local changes: {manifest['dirty']}")
    print("Untracked files are excluded from the source archive; retain required local helpers separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
