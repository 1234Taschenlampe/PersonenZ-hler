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


def test_quiet_live_scene_is_not_a_frozen_stream() -> None:
    detector = CameraObstructionDetector()
    rng = np.random.default_rng(42)
    image = rng.integers(40, 200, (36, 64), dtype=np.uint8)
    for index in range(20):
        frame = image.copy()
        frame[index % 36, index % 64] += 1
        assert not detector.update(frame).obstructed


def test_repeated_identical_frames_still_detect_frozen_stream() -> None:
    detector = CameraObstructionDetector()
    image = np.random.default_rng(42).integers(40, 200, (36, 64), dtype=np.uint8)
    assert not detector.update(image).obstructed
    assert not detector.update(image).obstructed
    for _ in range(5):
        result = detector.update(image)
    assert result.obstructed
    assert result.reason == "frozen frame"
