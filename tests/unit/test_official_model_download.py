from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

import visitor_counter.model_installation as mi
from visitor_counter.model_installation import ModelInstallationError, ModelInstallationService
from visitor_counter.runtime_paths import RuntimePaths


MODEL_URL = (
    "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/"
    "ModelZoo/Compiled/v5.4.0/hailo10h/yolo26m.hef"
)
DATA = b"HEF_BINARY_TEST_FIXTURE_NOT_REAL" * 256


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, url: str = MODEL_URL):
        super().__init__(data)
        self._url = url

    def geturl(self) -> str:
        return self._url


def _installer(tmp_path: Path, *, url: str = MODEL_URL) -> ModelInstallationService:
    manifest_dir = tmp_path / "models" / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "yolo26m_detection_hailo10h_manifest.json").write_text(
        json.dumps({"hef_source_url": url, "hef_sha256": hashlib.sha256(DATA).hexdigest()})
    )
    return ModelInstallationService(RuntimePaths.discover(
        tmp_path,
        environ={"PERSONENZAEHLER_MODEL_DIR": str(tmp_path / "models")},
        home=tmp_path,
    ))


def test_verified_official_download_installs_and_rerun_skips(monkeypatch, tmp_path: Path) -> None:
    installer = _installer(tmp_path)
    opened = []

    def get(request, *, timeout: float):
        opened.append(request.full_url)
        return FakeResponse(DATA)

    monkeypatch.setattr(mi, "urlopen", get)
    result = installer.download_official("detector")
    assert result.path.read_bytes() == DATA
    assert result.path.name == "yolo26m_detection_hailo10h_640.hef"
    assert installer.download_official("detector") == result
    assert opened == [MODEL_URL]


def test_hash_mismatch_keeps_target_absent(monkeypatch, tmp_path: Path) -> None:
    installer = _installer(tmp_path)
    monkeypatch.setattr(mi, "urlopen", lambda *a, **k: FakeResponse(b"E" * 4096))
    with pytest.raises(ModelInstallationError, match="SHA-256"):
        installer.download_official("detector")
    assert not (tmp_path / "models" / installer.TARGETS["detector"]).exists()


def test_existing_model_is_not_overwritten(monkeypatch, tmp_path: Path) -> None:
    installer = _installer(tmp_path)
    target = tmp_path / "models" / installer.TARGETS["detector"]
    target.write_bytes(b"X" * 4096)
    monkeypatch.setattr(mi, "urlopen", lambda *a, **k: pytest.fail("must not download"))
    with pytest.raises(ModelInstallationError, match="nicht die freigegebene"):
        installer.download_official("detector")
    assert target.read_bytes() == b"X" * 4096


def test_refuses_untrusted_manifest_url(tmp_path: Path) -> None:
    installer = _installer(tmp_path, url="https://example.invalid/file.hef")
    with pytest.raises(ModelInstallationError, match="Unsichere"):
        installer.download_official("detector")


def test_refuses_redirect_to_unknown_host(monkeypatch, tmp_path: Path) -> None:
    installer = _installer(tmp_path)
    monkeypatch.setattr(mi, "urlopen", lambda *a, **k: FakeResponse(DATA, "https://evil.test/a.hef"))
    with pytest.raises(ModelInstallationError, match="Weiterleitung"):
        installer.download_official("detector")
    assert not (tmp_path / "models" / installer.TARGETS["detector"]).exists()


def test_official_source_uses_pinned_repository_manifest(tmp_path: Path) -> None:
    installer = _installer(tmp_path)
    url, digest = installer._official_source("detector")
    assert url == MODEL_URL
    assert digest == hashlib.sha256(DATA).hexdigest()
