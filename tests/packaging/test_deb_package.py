import tarfile
from io import BytesIO
from pathlib import Path

import yaml

from scripts.build_deb import build


def _ar_members(data: bytes) -> dict[str, bytes]:
    assert data.startswith(b"!<arch>\n")
    position = 8
    result: dict[str, bytes] = {}
    while position < len(data):
        header = data[position : position + 60]
        assert header[58:60] == b"`\n"
        name = header[:16].decode("ascii").strip().removesuffix("/")
        size = int(header[48:58].decode("ascii").strip())
        start = position + 60
        result[name] = data[start : start + size]
        position = start + size + (size % 2)
    return result


def test_debian_package_contains_desktop_service_policy_and_no_private_key(
    tmp_path: Path,
) -> None:
    output = build(tmp_path / "personenzaehler.deb", "1.0.0", "arm64", 1_700_000_000)
    members = _ar_members(output.read_bytes())
    assert set(members) == {"debian-binary", "control.tar.gz", "data.tar.gz"}
    with tarfile.open(fileobj=BytesIO(members["data.tar.gz"]), mode="r:gz") as archive:
        names = set(archive.getnames())
        assert "usr/bin/personenzaehler" in names
        assert "usr/lib/systemd/system/personenzaehler.service" in names
        assert "usr/share/applications/de.personenzaehler.Desktop.desktop" in names
        assert "usr/share/polkit-1/actions/de.personenzaehler.policy" in names
        assert "usr/share/personenzaehler/license_public_key.pem" in names
        assert "usr/share/doc/personenzaehler/INSTALLATION.md" in names
        assert "usr/share/doc/personenzaehler/SECURITY_REVIEW.md" in names
        config_member = archive.extractfile("etc/personenzaehler/config.yaml")
        assert config_member is not None
        config = yaml.safe_load(config_member.read())
        assert (
            config["database"]["path"]
            == "/var/lib/personenzaehler/person_counter.sqlite3"
        )
        assert config["model"]["hef_path"].startswith(
            "/var/lib/personenzaehler/models/"
        )
        service_member = archive.extractfile(
            "usr/lib/systemd/system/personenzaehler.service"
        )
        assert service_member is not None
        service = service_member.read().decode("utf-8")
        assert "VISITOR_COUNTER_LICENSE_REQUIRED=1" in service
        assert "VISITOR_COUNTER_LICENSE_ONLINE_REQUIRED=0" in service
        assert not any(
            "private" in name.lower() and "privacy" not in name.lower()
            for name in names
        )


def test_debian_package_is_reproducible(tmp_path: Path) -> None:
    first = build(tmp_path / "first.deb", "1.0.0", "arm64", 1_700_000_000)
    second = build(tmp_path / "second.deb", "1.0.0", "arm64", 1_700_000_000)
    assert first.read_bytes() == second.read_bytes()
