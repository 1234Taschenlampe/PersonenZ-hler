from __future__ import annotations

import json
from pathlib import Path

import pytest

from visitor_counter.configuration import AppConfig
from visitor_counter.runtime_paths import RuntimePaths
from visitor_counter.security_assets import SecurityAssetError, SecurityAssetService


def _paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths.discover(
        tmp_path,
        environ={
            "PERSONENZAEHLER_CONFIG_FILE": str(tmp_path / "config" / "config.yaml"),
            "PERSONENZAEHLER_DATA_DIR": str(tmp_path / "data"),
            "PERSONENZAEHLER_LOG_DIR": str(tmp_path / "logs"),
            "PERSONENZAEHLER_CACHE_DIR": str(tmp_path / "cache"),
            "PERSONENZAEHLER_STATE_DIR": str(tmp_path / "state"),
        },
        home=tmp_path,
    )


def test_tls_assets_are_copied_to_fixed_local_targets(tmp_path: Path) -> None:
    source = tmp_path / "selected.pem"
    source.write_text("-----BEGIN TEST-----\n" + "x" * 64, encoding="utf-8")

    installed = SecurityAssetService(_paths(tmp_path)).install_tls_asset(
        "certificate", source
    )

    assert installed == tmp_path / "config" / "tls.crt"
    assert installed.read_bytes() == source.read_bytes()


def test_pairing_export_requires_remote_binding(tmp_path: Path) -> None:
    config = AppConfig()
    service = SecurityAssetService(_paths(tmp_path))

    with pytest.raises(SecurityAssetError, match="Netzwerkbindung"):
        service.export_pairing(config, tmp_path / "pairing.json")


def test_pairing_export_contains_viewer_role_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "v" * 48
    monkeypatch.setenv("VISITOR_COUNTER_VIEWER_TOKEN", token)
    config = AppConfig()
    config.api.bind_host = "192.0.2.25"
    config.api.port = 8766
    destination = tmp_path / "pairing.json"

    SecurityAssetService(_paths(tmp_path)).export_pairing(config, destination)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["base_url"] == "https://192.0.2.25:8766"
    assert payload["viewer_token"] == token
    assert "operator" not in payload
    assert "admin" not in payload
