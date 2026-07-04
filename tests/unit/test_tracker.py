from __future__ import annotations

from visitor_counter.configuration import TrackingConfig
from visitor_counter.tracker import IoUFallbackTracker
from visitor_counter.types import BoundingBox, Detection, TrackState


def test_tracker_keeps_id_for_overlapping_detection() -> None:
    tracker = IoUFallbackTracker(TrackingConfig())
    first = tracker.update("camera_1", [Detection(BoundingBox(0, 0, 100, 100), 0.9)])
    second = tracker.update("camera_1", [Detection(BoundingBox(5, 5, 105, 105), 0.9)])
    assert first[0].track_id == second[0].track_id


def test_tracker_confirms_only_after_min_hits() -> None:
    tracker = IoUFallbackTracker(TrackingConfig(min_confirmed_hits=3))
    states = []
    for offset in range(3):
        tracks = tracker.update("camera_1", [Detection(BoundingBox(offset, 0, 100 + offset, 100), 0.9)])
        states.append(tracks[0].state)
    assert states[:2] == [TrackState.TENTATIVE, TrackState.TENTATIVE]
    assert states[2] is TrackState.CONFIRMED


def test_tracker_uses_one_detection_per_track() -> None:
    tracker = IoUFallbackTracker(TrackingConfig(min_confirmed_hits=1))
    tracker.update("camera_1", [Detection(BoundingBox(0, 0, 50, 100), 0.9), Detection(BoundingBox(100, 0, 150, 100), 0.9)])
    tracks = tracker.update("camera_1", [Detection(BoundingBox(4, 0, 54, 100), 0.9), Detection(BoundingBox(104, 0, 154, 100), 0.9)])
    assert len({track.track_id for track in tracks if track.lost_frames == 0}) == 2
