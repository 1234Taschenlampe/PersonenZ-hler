from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import subprocess
import tarfile
import tomllib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PackageEntry:
    name: str
    data: bytes
    mode: int = 0o644


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def _entry(source: Path, destination: str, mode: int = 0o644) -> PackageEntry:
    return PackageEntry(destination.lstrip("/"), _bytes(source), mode)


def _source_date_epoch() -> int:
    configured = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if configured:
        return max(0, int(configured))
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%ct"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return max(0, int(result.stdout.strip()))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def project_version() -> str:
    return str(
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ]
    )


def installed_config() -> bytes:
    source = ROOT / "config" / "config.example.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    payload["database"]["path"] = "/var/lib/personenzaehler/person_counter.sqlite3"
    payload["model"]["hef_path"] = (
        "/var/lib/personenzaehler/models/yolo26m_detection_hailo10h_640.hef"
    )
    payload["model"]["target_hef_path"] = payload["model"]["hef_path"]
    payload["model"]["custom_target_hef_path"] = payload["model"]["hef_path"]
    payload["model"]["reid_hef_path"] = (
        "/var/lib/personenzaehler/models/osnet_x1_0_hailo10h.hef"
    )
    payload["model"]["postprocess_onnx_path"] = (
        "/usr/lib/personenzaehler/models/yolo26m_postprocessing.onnx"
    )
    payload["model"]["postprocess_config_path"] = (
        "/usr/lib/personenzaehler/models/config_onnx_yolo26m.json"
    )
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")


def data_entries() -> list[PackageEntry]:
    entries: list[PackageEntry] = []
    for source in sorted((ROOT / "src" / "visitor_counter").rglob("*.py")):
        if "__pycache__" in source.parts:
            continue
        relative = source.relative_to(ROOT / "src")
        entries.append(
            _entry(source, f"usr/lib/personenzaehler/src/{relative.as_posix()}")
        )
    for source in (
        ROOT / "scripts" / "status_api.py",
        ROOT / "scripts" / "__init__.py",
    ):
        entries.append(_entry(source, f"usr/lib/personenzaehler/scripts/{source.name}"))
    for source in sorted((ROOT / "models").rglob("*")):
        if not source.is_file() or source.suffix.lower() == ".hef":
            continue
        relative = source.relative_to(ROOT / "models")
        entries.append(
            _entry(source, f"usr/lib/personenzaehler/models/{relative.as_posix()}")
        )
    for name in (
        "ARCHITECTURE.md",
        "FEATURE_HISTORY_AUDIT.md",
        "INSTALLATION.md",
        "USER_MANUAL.md",
        "SECURITY_REVIEW.md",
        "PRIVACY_AND_SECURITY.md",
        "LICENSE_SYSTEM.md",
        "MODEL_SOURCES_AND_CREDITS.md",
    ):
        source = ROOT / "docs" / name
        if source.is_file():
            entries.append(_entry(source, f"usr/share/doc/personenzaehler/{name}"))
    entries.append(
        _entry(ROOT / "CHANGELOG.md", "usr/share/doc/personenzaehler/CHANGELOG.md")
    )

    linux = ROOT / "packaging" / "linux"
    entries.extend(
        [
            _entry(linux / "personenzaehler", "usr/bin/personenzaehler", 0o755),
            _entry(
                linux / "personenzaehler-service",
                "usr/bin/personenzaehler-service",
                0o755,
            ),
            _entry(linux / "personenzaehler-api", "usr/bin/personenzaehler-api", 0o755),
            _entry(
                linux / "personenzaehler-admin",
                "usr/lib/personenzaehler/personenzaehler-admin",
                0o755,
            ),
            _entry(
                linux / "personenzaehler.service",
                "usr/lib/systemd/system/personenzaehler.service",
            ),
            _entry(
                linux / "personenzaehler-api.service",
                "usr/lib/systemd/system/personenzaehler-api.service",
            ),
            _entry(
                linux / "de.personenzaehler.Desktop.desktop",
                "usr/share/applications/de.personenzaehler.Desktop.desktop",
            ),
            _entry(
                linux / "de.personenzaehler.Desktop.svg",
                "usr/share/icons/hicolor/scalable/apps/de.personenzaehler.Desktop.svg",
            ),
            _entry(
                linux / "de.personenzaehler.license.xml",
                "usr/share/mime/packages/de.personenzaehler.license.xml",
            ),
            _entry(
                linux / "de.personenzaehler.policy",
                "usr/share/polkit-1/actions/de.personenzaehler.policy",
            ),
            _entry(
                ROOT / "config" / "license_public_key.pem",
                "usr/share/personenzaehler/license_public_key.pem",
            ),
            PackageEntry("etc/personenzaehler/config.yaml", installed_config(), 0o644),
        ]
    )
    return entries


def _tar_gz(entries: list[PackageEntry], epoch: int) -> bytes:
    output = BytesIO()
    with gzip.GzipFile(
        fileobj=output, mode="wb", mtime=epoch, filename=""
    ) as compressed:
        with tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
        ) as archive:
            directories: set[str] = set()
            for entry in entries:
                parent = Path(entry.name).parent
                for candidate in reversed(parent.parents):
                    if str(candidate) not in {".", ""}:
                        directories.add(candidate.as_posix().rstrip("/") + "/")
                if str(parent) not in {".", ""}:
                    directories.add(parent.as_posix().rstrip("/") + "/")
            for name in sorted(
                directories, key=lambda value: (value.count("/"), value)
            ):
                info = tarfile.TarInfo(name)
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = epoch
                archive.addfile(info)
            for entry in sorted(entries, key=lambda item: item.name):
                info = tarfile.TarInfo(entry.name)
                info.size = len(entry.data)
                info.mode = entry.mode
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = epoch
                archive.addfile(info, BytesIO(entry.data))
    return output.getvalue()


def _control_entries(
    version: str, architecture: str, installed_size: int, data: list[PackageEntry]
) -> list[PackageEntry]:
    template = (ROOT / "packaging" / "debian" / "control.in").read_text(
        encoding="utf-8"
    )
    control = (
        template.replace("@VERSION@", version)
        .replace("@ARCH@", architecture)
        .replace("Description:", f"Installed-Size: {installed_size}\nDescription:")
        .encode("utf-8")
    )
    md5sums = "".join(
        f"{hashlib.md5(entry.data).hexdigest()}  {entry.name}\n"
        for entry in sorted(data, key=lambda item: item.name)
    )
    return [
        PackageEntry("control", control),
        _entry(ROOT / "packaging" / "debian" / "postinst", "postinst", 0o755),
        _entry(ROOT / "packaging" / "debian" / "prerm", "prerm", 0o755),
        PackageEntry("conffiles", b"/etc/personenzaehler/config.yaml\n"),
        PackageEntry("md5sums", md5sums.encode("ascii")),
    ]


def _ar_member(name: str, data: bytes, epoch: int) -> bytes:
    member_name = (name + "/")[:16].ljust(16)
    header = (
        member_name
        + str(epoch).ljust(12)
        + "0".ljust(6)
        + "0".ljust(6)
        + format(0o100644, "o").ljust(8)
        + str(len(data)).ljust(10)
        + "`\n"
    ).encode("ascii")
    return header + data + (b"\n" if len(data) % 2 else b"")


def build(output: Path, version: str, architecture: str, epoch: int) -> Path:
    data = data_entries()
    installed_size = max(1, (sum(len(entry.data) for entry in data) + 1023) // 1024)
    control = _control_entries(version, architecture, installed_size, data)
    package = bytearray(b"!<arch>\n")
    package.extend(_ar_member("debian-binary", b"2.0\n", epoch))
    package.extend(_ar_member("control.tar.gz", _tar_gz(control, epoch), epoch))
    package.extend(_ar_member("data.tar.gz", _tar_gz(data, epoch), epoch))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(package)
    temporary.replace(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a reproducible PersonenZähler Debian package"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", default=project_version())
    parser.add_argument("--architecture", default="arm64")
    args = parser.parse_args()
    output = (
        args.output
        or ROOT / "dist" / f"personenzaehler_{args.version}_{args.architecture}.deb"
    )
    package = build(
        output.resolve(), args.version, args.architecture, _source_date_epoch()
    )
    print(package)
    print(f"sha256={hashlib.sha256(package.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
