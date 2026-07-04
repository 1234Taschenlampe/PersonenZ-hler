from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .configuration import ModelConfig


class ModelUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelStatus:
    name: str
    path: Path
    exists: bool
    using_fallback: bool
    message: str
    target_name: str
    target_path: Path
    target_exists: bool
    sha256: str = ""
    model_type: str = "Detection"
    hailo_architecture: str = "HAILO10H required"
    postprocess_path: Path | None = None
    postprocess_exists: bool = False
    configured_model_name: str = ""
    configured_hef_path: Path | None = None
    hef_exists: bool = False
    hef_sha256: str = ""
    hef_loaded: bool = False
    inference_initialized: bool = False
    self_test_passed: bool = False
    active_model_name: str | None = None
    error_message: str = ""

    @property
    def active_display_name(self) -> str:
        if self.active_model_name:
            return self.active_model_name
        return "Nicht verfuegbar" if self.error_message else "Nicht geladen"

    @property
    def actual_hef_display(self) -> str:
        if self.active_model_name:
            return self.path.name
        return "Datei fehlt" if not self.hef_exists else "Nicht geladen"

    @property
    def sha256_display(self) -> str:
        return self.hef_sha256 if self.active_model_name and self.hef_sha256 else "Nicht verfuegbar"

    @property
    def inference_display(self) -> str:
        return "Aktiv" if self.inference_initialized and self.self_test_passed else "Inaktiv"


class ModelManager:
    def __init__(self, config: ModelConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root

    @property
    def hef_path(self) -> Path:
        path = Path(self.config.hef_path)
        return path if path.is_absolute() else self.project_root / path

    @property
    def target_hef_path(self) -> Path:
        path = Path(self.config.custom_target_hef_path)
        return path if path.is_absolute() else self.project_root / path

    @property
    def postprocess_onnx_path(self) -> Path | None:
        if not self.config.postprocess_onnx_path:
            return None
        path = Path(self.config.postprocess_onnx_path)
        return path if path.is_absolute() else self.project_root / path

    def status(self) -> ModelStatus:
        path = self.hef_path
        target_path = self.target_hef_path
        exists = path.exists() and path.is_file() and not path.is_symlink() and path.stat().st_size > 0
        target_exists = target_path.exists() and target_path.is_file() and not target_path.is_symlink() and target_path.stat().st_size > 0
        raw_path_exists = path.exists()
        postprocess_path = self.postprocess_onnx_path
        postprocess_exists = postprocess_path.exists() if postprocess_path else False
        digest = self._sha256(path) if exists else ""
        configured_target = path.resolve(strict=False) == target_path.resolve(strict=False)
        using_fallback = not configured_target or self.config.allow_fallback or self.config.detector_fallback_enabled
        if exists and configured_target and not using_fallback:
            message = f"Custom YOLO26x COCO HEF exists; runtime Hailo self-test has not run: {path}"
            error_message = ""
        elif using_fallback:
            message = "Detector inactive: only models/yolo26x_person_hailo10h_640.hef is allowed in production; COCO class 0 person is filtered"
            error_message = message
        elif raw_path_exists and path.is_symlink():
            message = f"Detector inactive: configured HEF is a symlink and is rejected: {path}"
            error_message = message
        else:
            message = f"Die erforderliche HEF fehlt: {target_path}"
            error_message = f"YOLO26x nicht verfuegbar: erforderliche Custom-HEF fehlt: {target_path}"
        return ModelStatus(
            self.config.model_name,
            path,
            exists,
            using_fallback,
            message,
            self.config.custom_target_model_name,
            target_path,
            target_exists,
            digest,
            self.config.model_type,
            "HAILO10H required",
            postprocess_path,
            postprocess_exists,
            self.config.model_name,
            path,
            exists,
            digest,
            False,
            False,
            False,
            None,
            error_message,
        )

    def require_available(self) -> ModelStatus:
        status = self.status()
        if status.using_fallback:
            raise ModelUnavailableError("Silent model fallback is disabled; refusing to load any non-custom YOLO26x HEF")
        if not status.exists:
            raise ModelUnavailableError(status.message)
        expected_name = self.target_hef_path.name
        if status.path.name != expected_name:
            raise ModelUnavailableError(f"Unexpected HEF name {status.path.name}; expected {expected_name}")
        return status

    def _sha256(self, path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
