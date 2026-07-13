from __future__ import annotations

from pathlib import Path
import os
from typing import Iterable, Protocol

import cv2
import numpy as np


class _Box(Protocol):
    x1: float
    y1: float
    x2: float
    y2: float


class _Track(Protocol):
    bbox: _Box


def anonymize_frame(
    frame: np.ndarray,
    *,
    mode: str = "full_frame",
    pixel_size: int = 24,
    tracks: Iterable[_Track] = (),
) -> np.ndarray:
    """Return a copy in which identifying visual details are irreversibly obscured."""
    output = frame.copy()
    if mode == "none":
        return output
    if mode == "full_frame":
        return _pixelate(output, pixel_size)
    if mode != "persons":
        raise ValueError(f"Unsupported anonymization mode: {mode}")
    height, width = output.shape[:2]
    for track in tracks:
        box = track.bbox
        x1 = max(0, min(width - 1, int(box.x1)))
        y1 = max(0, min(height - 1, int(box.y1)))
        x2 = max(0, min(width, int(box.x2)))
        y2 = max(0, min(height, int(box.y2)))
        if x2 > x1 and y2 > y1:
            output[y1:y2, x1:x2] = _pixelate(output[y1:y2, x1:x2], pixel_size)
    return output


def hidden_preview(frame: np.ndarray) -> np.ndarray:
    output = np.zeros_like(frame)
    height, width = output.shape[:2]
    text = "DATENSCHUTZMODUS - BILDVORSCHAU AUS"
    cv2.putText(
        output,
        text,
        (max(12, width // 12), max(40, height // 2)),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.55, min(width, height) / 900),
        (210, 210, 210),
        2,
        cv2.LINE_AA,
    )
    return output


def stream_frame_directory(project_root: Path) -> Path:
    """Prefer a RAM-backed directory on Linux so stream images never hit persistent storage."""
    runtime_root = Path("/dev/shm")
    if runtime_root.is_dir():
        user_id = os.getuid() if hasattr(os, "getuid") else "local"
        return runtime_root / f"visitor-counter-stream-{user_id}"
    return project_root / "data" / "runtime_stream_frames"


def _pixelate(image: np.ndarray, pixel_size: int) -> np.ndarray:
    height, width = image.shape[:2]
    block = max(8, int(pixel_size))
    small = cv2.resize(
        image,
        (max(1, width // block), max(1, height // block)),
        interpolation=cv2.INTER_AREA,
    )
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
