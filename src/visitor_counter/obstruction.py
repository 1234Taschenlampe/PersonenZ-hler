from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ObstructionResult:
    obstructed: bool
    reason: str
    stable_frames: int


class CameraObstructionDetector:
    def __init__(self, release_stable_frames: int = 10) -> None:
        self.release_stable_frames = release_stable_frames
        self._previous_gray: np.ndarray | None = None
        self._stable_frames = 0
        self._latched = False

    def update(self, image: np.ndarray) -> ObstructionResult:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)
        brightness = float(np.mean(small))
        contrast = float(np.std(small))
        structure = float(cv2.Laplacian(small, cv2.CV_64F).var())
        frozen = self._is_frozen(small)
        abrupt = self._is_abrupt_change(small)
        self._previous_gray = small.copy()

        reason = ""
        if contrast < 3.0 and structure < 2.0:
            reason = "low texture / covered lens"
        elif brightness < 8.0 or brightness > 247.0:
            reason = "extreme brightness"
        elif structure < 1.0:
            reason = "severe blur or close obstruction"
        elif frozen:
            reason = "frozen frame"
        elif abrupt and structure < 8.0:
            reason = "abrupt low-structure occlusion"

        if reason:
            self._latched = True
            self._stable_frames = 0
            return ObstructionResult(True, reason, self._stable_frames)

        self._stable_frames += 1
        if self._latched and self._stable_frames < self.release_stable_frames:
            return ObstructionResult(True, "waiting for stable frames after obstruction", self._stable_frames)
        self._latched = False
        return ObstructionResult(False, "clear", self._stable_frames)

    def _is_frozen(self, small_gray: np.ndarray) -> bool:
        if self._previous_gray is None:
            return False
        diff = float(np.mean(cv2.absdiff(small_gray, self._previous_gray)))
        return diff < 0.05

    def _is_abrupt_change(self, small_gray: np.ndarray) -> bool:
        if self._previous_gray is None:
            return False
        diff = float(np.mean(cv2.absdiff(small_gray, self._previous_gray)))
        return diff > 55.0
