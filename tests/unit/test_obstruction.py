from __future__ import annotations

import numpy as np

from visitor_counter.obstruction import CameraObstructionDetector


def test_black_cover_is_obstruction() -> None:
    detector = CameraObstructionDetector()
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    result = detector.update(image)
    assert result.obstructed


def test_release_requires_stable_frames() -> None:
    detector = CameraObstructionDetector(release_stable_frames=3)
    detector.update(np.zeros((120, 160, 3), dtype=np.uint8))
    textured = np.indices((120, 160)).sum(axis=0).astype(np.uint8)
    image = np.dstack([textured, np.roll(textured, 3, axis=1), np.roll(textured, 5, axis=0)])
    assert detector.update(image).obstructed
    assert detector.update(np.roll(image, 1, axis=1)).obstructed
    assert not detector.update(np.roll(image, 2, axis=1)).obstructed
