from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from threading import Condition, Event, Thread
from time import monotonic, time
from typing import Iterable

import cv2
import numpy as np

from .privacy import anonymize_frame, stream_frame_directory

LOGGER = logging.getLogger(__name__)


class FrameStreamExporter:
    """Export anonymized, short-lived frames for an explicitly enabled local API."""

    def __init__(
        self,
        project_root: Path,
        *,
        enabled: bool = False,
        anonymization_mode: str = "full_frame",
        pixel_size: int = 24,
        remove_on_shutdown: bool = True,
        max_width: int = 640,
        max_height: int = 360,
        jpeg_quality: int = 65,
        target_fps: float = 5.0,
    ) -> None:
        self.enabled = enabled
        self.output_dir = stream_frame_directory(project_root)
        self.anonymization_mode = anonymization_mode
        self.pixel_size = pixel_size
        self.remove_on_shutdown = remove_on_shutdown
        self.max_width = max_width
        self.max_height = max_height
        self.jpeg_quality = jpeg_quality
        self.target_fps = target_fps
        self._min_interval = 1.0 / max(target_fps, 1.0)
        self._last_submit_at: dict[str, float] = {}
        self._pending: dict[str, tuple[np.ndarray, tuple[object, ...]]] = {}
        self._condition = Condition()
        self._stop = Event()
        self._thread: Thread | None = None
        if not enabled:
            self._remove_output_dir()
            return
        if anonymization_mode == "none":
            raise ValueError("A video stream may not be enabled without anonymization.")
        if self.output_dir.is_symlink():
            raise RuntimeError(f"Refusing a symlinked stream directory: {self.output_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        _set_mode(self.output_dir, 0o700)
        self._thread = Thread(target=self._run, name="frame-stream-exporter", daemon=True)
        self._thread.start()

    def submit(self, camera_id: str, frame: np.ndarray, tracks: Iterable[object] = ()) -> None:
        if not self.enabled:
            return
        now = monotonic()
        if now - self._last_submit_at.get(camera_id, 0.0) < self._min_interval:
            return
        self._last_submit_at[camera_id] = now
        with self._condition:
            self._pending[camera_id] = (frame.copy(), tuple(tracks))
            self._condition.notify()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._pending.clear()
            self._condition.notify_all()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.remove_on_shutdown:
            self._remove_output_dir()

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._condition:
                while not self._pending and not self._stop.is_set():
                    self._condition.wait(timeout=0.5)
                pending = self._pending
                self._pending = {}
            for camera_id, (frame, tracks) in pending.items():
                try:
                    self._write_frame(camera_id, frame, tracks)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("STREAM_EXPORT_FAILED camera=%s error_type=%s", camera_id, type(exc).__name__)

    def _write_frame(self, camera_id: str, frame: np.ndarray, tracks: Iterable[object]) -> None:
        frame = anonymize_frame(
            frame,
            mode=self.anonymization_mode,
            pixel_size=self.pixel_size,
            tracks=tracks,
        )
        frame = self._resize(frame)
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        jpg_path = self.output_dir / f"{camera_id}.jpg"
        meta_path = self.output_dir / f"{camera_id}.json"
        jpg_tmp = jpg_path.with_suffix(".jpg.tmp")
        meta_tmp = meta_path.with_suffix(".json.tmp")
        data = encoded.tobytes()
        jpg_tmp.write_bytes(data)
        _set_mode(jpg_tmp, 0o600)
        jpg_tmp.replace(jpg_path)
        height, width = frame.shape[:2]
        meta_tmp.write_text(
            json.dumps(
                {
                    "camera_id": camera_id,
                    "written_at": time(),
                    "width": width,
                    "height": height,
                    "bytes": len(data),
                    "anonymized": True,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        _set_mode(meta_tmp, 0o600)
        meta_tmp.replace(meta_path)
        _set_mode(jpg_path, 0o600)
        _set_mode(meta_path, 0o600)

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        scale = min(self.max_width / max(width, 1), self.max_height / max(height, 1), 1.0)
        if scale >= 1.0:
            return frame
        return cv2.resize(
            frame,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    def _remove_output_dir(self) -> None:
        try:
            if self.output_dir.is_dir():
                shutil.rmtree(self.output_dir)
        except OSError:
            pass


def _set_mode(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass
