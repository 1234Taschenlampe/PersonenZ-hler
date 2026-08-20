from pathlib import Path

import pytest

from visitor_counter.model_installation import (
    ModelInstallationError,
    ModelInstallationService,
)
from visitor_counter.runtime_paths import RuntimePaths


def test_development_model_import_uses_fixed_product_filename(tmp_path: Path) -> None:
    source = tmp_path / "uploaded.hef"
    source.write_bytes(b"H" * 4096)
    paths = RuntimePaths.discover(
        tmp_path,
        environ={"PERSONENZAEHLER_MODEL_DIR": str(tmp_path / "models")},
        home=tmp_path,
    )
    result = ModelInstallationService(paths).install("detector", source)
    assert result.path == tmp_path / "models" / "yolo26m_detection_hailo10h_640.hef"
    assert result.path.read_bytes() == source.read_bytes()


def test_model_import_rejects_wrong_extension_and_unknown_kind(tmp_path: Path) -> None:
    source = tmp_path / "model.bin"
    source.write_bytes(b"x" * 4096)
    service = ModelInstallationService(
        RuntimePaths.discover(tmp_path, environ={}, home=tmp_path)
    )
    with pytest.raises(ModelInstallationError):
        service.install("detector", source)
    source = tmp_path / "model.hef"
    source.write_bytes(b"x" * 4096)
    with pytest.raises(ModelInstallationError):
        service.install("other", source)
