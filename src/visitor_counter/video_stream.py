from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Condition, Event, Thread
from time import monotonic, time

import cv2
import numpy as np

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamFrameMeta:
    camera_id: str
    frame_id: int
    source: str
    timestamp: float
    width: int
    height: int
    jpeg_quality: int
    bytes: int
    target_fps: float


class FrameStreamExporter:
    """Exports the already-running GUI/pipeline frames for the mobile API."""

    def __init__(
        self,
        project_root: Path,
        max_width: int = 640,
        max_height: int = 360,
        jpeg_quality: int = 72,
        target_fps: float = 12.0,
    ) -> None:
        self.output_dir = project_root / "data" / "stream_frames"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_width = max_width
        self.max_height = max_height
        self.jpeg_quality = jpeg_quality
        self.target_fps = target_fps
        self._min_interval = 1.0 / max(target_fps, 1.0)
        self._last_submit_at: dict[str, float] = {}
        self._last_processed_at: dict[str, float] = {}
        self._pending: dict[str, tuple[np.ndarray, int, str, float]] = {}
        self._condition = Condition()
        self._stop = Event()
        self._thread = Thread(target=self._run, name="frame-stream-exporter", daemon=True)
        self._thread.start()

    def submit(self, camera_id: str, frame: np.ndarray, frame_id: int, source: str) -> None:
        now = monotonic()
        if source == "raw" and now - self._last_processed_at.get(camera_id, 0.0) < 0.75:
            return
        if now - self._last_submit_at.get(camera_id, 0.0) < self._min_interval:
            return
        if source == "processed":
            self._last_processed_at[camera_id] = now
        self._last_submit_at[camera_id] = now

        with self._condition:
            self._pending[camera_id] = (frame.copy(), frame_id, source, time())
            self._condition.notify()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._condition:
                while not self._pending and not self._stop.is_set():
                    self._condition.wait(timeout=0.5)
                pending = self._pending
                self._pending = {}

            for camera_id, (frame, frame_id, source, captured_at) in pending.items():
                try:
                    self._write_frame(camera_id, frame, frame_id, source, captured_at)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("STREAM_EXPORT_FAILED camera=%s error=%s", camera_id, exc)

    def _write_frame(self, camera_id: str, frame: np.ndarray, frame_id: int, source: str, captured_at: float) -> None:
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
        jpg_tmp.replace(jpg_path)

        height, width = frame.shape[:2]
        meta = StreamFrameMeta(
            camera_id=camera_id,
            frame_id=frame_id,
            source=source,
            timestamp=captured_at,
            width=width,
            height=height,
            jpeg_quality=self.jpeg_quality,
            bytes=len(data),
            target_fps=self.target_fps,
        )
        meta_tmp.write_text(json.dumps(asdict(meta), sort_keys=True), encoding="utf-8")
        meta_tmp.replace(meta_path)

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        scale = min(self.max_width / max(width, 1), self.max_height / max(height, 1), 1.0)
        if scale >= 1.0:
            return frame
        target_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)
