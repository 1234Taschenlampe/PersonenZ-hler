from __future__ import annotations

from visitor_counter.counter import GlobalCounts, LineCrossingCounter
from visitor_counter.types import BoundingBox, CountingLine, Direction, TrackedObject, TrackState
from visitor_counter.configuration import TrackingConfig, CameraConfig


def _track(track_id: int, y: float, hits: int = 5, state: TrackState = TrackState.CONFIRMED) -> TrackedObject:
    return TrackedObject(
        track_id=track_id,
        bbox=BoundingBox(10, y - 5, 30, y + 5),
        confidence=0.9,
        camera_id="camera_1",
        hits=hits,
        state=state,
    )


def _create_counter(camera_id: str, line: CountingLine, min_stable: int = 1, role: str = "entrance") -> LineCrossingCounter:
    tracking_config = TrackingConfig(
        min_stable_zone_frames=min_stable,
        zone_hysteresis_pixels=0.0,
        min_confirmed_track_hits=2,
        minimum_confidence=0.0,
        minimum_bbox_area=0.0,
        count_cooldown_seconds=0.0
    )
    camera_config = CameraConfig(
        camera_id=camera_id,
        role=role,
        entry_direction="A_to_B",
        exit_direction="B_to_A"
    )
    return LineCrossingCounter(camera_id, line, tracking_config, camera_config)


def test_line_crossing_counts_in_direction() -> None:
    counter = _create_counter("camera_1", CountingLine((0, 100), (100, 100), in_positive_side=True), 1, "entrance")
    assert counter.update(1, [_track(1, 80)]) == []
    events = counter.update(2, [_track(1, 120)])
    assert len(events) == 1
    assert events[0].direction is Direction.IN
    assert counter.counts.entered == 1
    assert counter.counts.inside == 1


def test_line_crossing_counts_out_direction() -> None:
    counter = _create_counter("camera_2", CountingLine((0, 100), (100, 100), in_positive_side=True), 1, "exit")
    counter.update(1, [_track(1, 120)])
    events = counter.update(2, [_track(1, 80)])
    assert len(events) == 1
    assert events[0].direction is Direction.OUT
    assert counter.counts.exited == 1
    assert counter.counts.inside == 0


def test_global_count_never_negative() -> None:
    counts = GlobalCounts()
    counts.apply(Direction.OUT, counted=True, uncertain=False)
    assert counts.inside == 0


def test_sitting_person_does_not_create_passage() -> None:
    counter = _create_counter("camera_1", CountingLine((0, 100), (100, 100), in_positive_side=True), 3, "entrance")
    for frame_id in range(1, 8):
        assert counter.update(frame_id, [_track(1, 80)]) == []
    assert counter.counts.entered == 0


def test_bbox_jitter_near_line_does_not_create_passage() -> None:
    counter = _create_counter("camera_1", CountingLine((0, 100), (100, 100), in_positive_side=True), 3, "entrance")
    for frame_id, y in enumerate([96, 98, 97, 99, 98, 96], start=1):
        assert counter.update(frame_id, [_track(1, y)]) == []
    assert counter.counts.entered == 0


def test_tentative_track_does_not_count() -> None:
    counter = _create_counter("camera_1", CountingLine((0, 100), (100, 100), in_positive_side=True), 1, "entrance")
    counter.update(1, [_track(1, 80, hits=1, state=TrackState.TENTATIVE)])
    events = counter.update(2, [_track(1, 120, hits=2, state=TrackState.TENTATIVE)])
    assert events == []
