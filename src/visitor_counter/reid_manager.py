from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from .configuration import ModelConfig
from .model_manager import ModelUnavailableError
from .types import BoundingBox


@dataclass(frozen=True)
class ReIDStatus:
    name: str
    path: Path
    exists: bool
    ready: bool
    message: str
    sha256: str = ""
    input_tensors: tuple[str, ...] = ()
    output_tensors: tuple[str, ...] = ()


class OSNetReIDManager:
    def __init__(self, config: ModelConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self.ready = False
        self.status_message = "not initialized"
        self.last_latency_ms = 0.0
        self.inference_count = 0
        self.error_count = 0
        self.cache_hits = 0
        self.match_successes = 0
        self.uncertain_matches = 0
        self.rejected_matches = 0
        self._hailo_module: object | None = None
        self._hef: object | None = None
        self._vdevice: object | None = None
        self._infer_model: object | None = None
        self._configured_model: object | None = None
        self._config_ctx: object | None = None
        self._input_name: str | None = None

    @property
    def hef_path(self) -> Path:
        path = Path(self.config.reid_hef_path)
        return path if path.is_absolute() else self.project_root / path

    def status(self, validate_hailo: bool = False) -> ReIDStatus:
        path = self.hef_path
        if not path.exists():
            return ReIDStatus(
                self.config.reid_model_name,
                path,
                False,
                False,
                f"OSNet ReID HEF fehlt: {path}",
            )
        if path.is_symlink():
            return ReIDStatus(
                self.config.reid_model_name,
                path,
                True,
                False,
                f"OSNet ReID HEF ist ein Symlink und wird abgelehnt: {path}",
            )
        if not path.is_file() or path.stat().st_size <= 0:
            return ReIDStatus(
                self.config.reid_model_name,
                path,
                True,
                False,
                f"OSNet ReID HEF ist keine nicht-leere regulaere Datei: {path}",
            )
        digest = _sha256_file(path)
        if not validate_hailo:
            return ReIDStatus(
                self.config.reid_model_name,
                path,
                True,
                True,
                "OSNet ReID HEF vorhanden; Hailo-Tensorpruefung steht noch aus",
                digest,
            )
        try:
            import hailo_platform  # type: ignore[import-not-found]

            hef = hailo_platform.HEF(str(path))
            inputs = tuple(info.name for info in hef.get_input_vstream_infos())
            outputs = tuple(info.name for info in hef.get_output_vstream_infos())
        except Exception as exc:  # noqa: BLE001
            return ReIDStatus(
                self.config.reid_model_name,
                path,
                True,
                False,
                f"OSNet ReID HEF konnte von HailoRT nicht gelesen werden: {exc}",
                digest,
            )
        if not inputs or not outputs:
            return ReIDStatus(
                self.config.reid_model_name,
                path,
                True,
                False,
                "OSNet ReID HEF hat keine erkennbaren Hailo-Ein- oder Ausgangstensoren",
                digest,
                inputs,
                outputs,
            )
        return ReIDStatus(self.config.reid_model_name, path, True, True, "OSNet ReID HEF Hailo-lesbar", digest, inputs, outputs)

    def require_available(self, validate_hailo: bool = True) -> ReIDStatus:
        status = self.status(validate_hailo=validate_hailo)
        if not status.ready:
            raise ModelUnavailableError(status.message)
        return status

    def initialize(self) -> None:
        status = self.require_available(validate_hailo=True)
        try:
            import hailo_platform  # type: ignore[import-not-found]

            self._hailo_module = hailo_platform
            params = hailo_platform.VDevice.create_params()
            if hasattr(params, "group_id"):
                params.group_id = "SHARED"
            self._vdevice = hailo_platform.VDevice(params)
            self._hef = hailo_platform.HEF(str(status.path))
            self._infer_model = self._vdevice.create_infer_model(str(status.path))
            self._infer_model.set_batch_size(1)
            self._infer_model.input().set_format_type(hailo_platform.FormatType.UINT8)
            for output_name in self._infer_model.output_names:
                self._infer_model.output(output_name).set_format_type(hailo_platform.FormatType.FLOAT32)
            self._config_ctx = self._infer_model.configure()
            self._configured_model = self._config_ctx.__enter__()
            self._input_name = self._infer_model.input_names[0]
        except Exception as exc:  # noqa: BLE001
            self.error_count += 1
            self.status_message = f"OSNet ReID initialization failed: {exc}"
            self.close()
            raise ModelUnavailableError(self.status_message) from exc
        self.ready = True
        self.status_message = f"{status.name} active ({status.sha256[:12]})"

    def infer_embedding(self, image: np.ndarray, bbox: BoundingBox) -> tuple[float, ...] | None:
        if not self.ready or self._infer_model is None or self._configured_model is None or self._input_name is None:
            return None
        crop = self._crop_person(image, bbox)
        if crop is None:
            return None
        tensor = self._preprocess(crop)
        start = perf_counter()
        try:
            output_buffers = {
                name: np.empty(self._infer_model.output(name).shape, dtype=np.float32)
                for name in self._infer_model.output_names
            }
            bindings = self._configured_model.create_bindings(output_buffers=output_buffers)
            bindings.input(self._input_name).set_buffer(tensor)
            self._configured_model.run([bindings], 10000)
            output = bindings.output(self._infer_model.output_names[0]).get_buffer()
        except Exception:
            self.error_count += 1
            return None
        self.last_latency_ms = (perf_counter() - start) * 1000.0
        self.inference_count += 1
        vector = np.asarray(output, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-6:
            return None
        return tuple((vector / norm).astype(np.float32).tolist())

    def close(self) -> None:
        if self._config_ctx is not None:
            try:
                self._config_ctx.__exit__(None, None, None)
            except Exception:
                pass
        self._config_ctx = None
        self._configured_model = None
        self._infer_model = None
        if self._vdevice is not None and hasattr(self._vdevice, "release"):
            try:
                self._vdevice.release()
            except Exception:
                pass
        self._vdevice = None
        self.ready = False

    def _crop_person(self, image: np.ndarray, bbox: BoundingBox) -> np.ndarray | None:
        height, width = image.shape[:2]
        x1 = max(0, min(width - 1, int(bbox.x1)))
        y1 = max(0, min(height - 1, int(bbox.y1)))
        x2 = max(0, min(width, int(bbox.x2)))
        y2 = max(0, min(height, int(bbox.y2)))
        if x2 <= x1 or y2 <= y1:
            return None
        return image[y1:y2, x1:x2]

    def _preprocess(self, crop: np.ndarray) -> np.ndarray:
        resized = cv2.resize(crop, (128, 256), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        return np.ascontiguousarray(rgb[np.newaxis, ...], dtype=np.uint8)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
