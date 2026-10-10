"""Edge-exit counting: direction from tracked movement, event only after disappearance."""
from __future__ import annotations

from visitor_counter.configuration import CameraConfig, TrackingConfig
from visitor_counter.counter import LineCrossingCounter
from visitor_counter.types import BoundingBox, CountingLine, Direction, TrackState, TrackedObject


def make_counter() -> LineCrossingCounter:
    camera = CameraConfig(
        camera_id="camera_1",
        width=200,
        height=200,
        line_start=(0, 100),
        line_end=(200, 100),
        counting_mode="exit_edge",
        entry_direction="A_to_B",
        exit_direction="B_to_A",
        disappearance_frames=3,
        edge_margin_pixels=40,
    )
    tracker = TrackingConfig(
        min_confirmed_track_hits=3,
        minimum_bbox_area=50,
        minimum_confidence=0.3,
    )
    return LineCrossingCounter(
        camera.camera_id, CountingLine(camera.line_start, camera.line_end),
        tracker, camera,
    )


def observed_track(y: int, track_id: int = 1) -> TrackedObject:
    return TrackedObject(
        track_id=track_id,
        bbox=BoundingBox(80, max(0, y - 22), 120, min(200, y + 25)),
        confidence=0.92,
        camera_id="camera_1",
        global_person_id=track_id + 100,
        hits=10,
        state=TrackState.CONFIRMED,
    )


def simulate(counter: LineCrossingCounter, positions: list[int]) -> list:
    events = []
    for frame_id, y in enumerate(positions, 1):
        events.extend(counter.update(frame_id, [observed_track(y)], (200, 200)))
    for frame_id in range(len(positions) + 1, len(positions) + 7):
        events.extend(counter.update(frame_id, [], (200, 200)))
    return events


def test_person_departing_bottom_counts_one_entry_only_on_disappearance() -> None:
    counter = make_counter()
    for frame_id, y in enumerate([35, 55, 78, 105, 135, 170, 190], 1):
        assert not counter.update(frame_id, [observed_track(y)], (200, 200))
    assert counter.counts.entered == 0
    assert not counter.update(8, [], (200, 200))
    assert not counter.update(9, [], (200, 200))
    result = counter.update(10, [], (200, 200))
    assert len(result) == 1
    assert result[0].direction == Direction.IN
    assert result[0].metadata["confirmed_at_exit_edge"] is True
    assert counter.counts.entered == 1
    assert not counter.update(11, [], (200, 200))
    assert counter.counts.entered == 1


def test_person_departing_top_counts_one_exit() -> None:
    counter = make_counter()
    events = simulate(counter, [175, 155, 126, 100, 75, 35, 8])
    assert len(events) == 1
    assert events[0].direction == Direction.OUT
    assert counter.counts.exited == 1


def test_mid_frame_disappearance_does_not_count() -> None:
    counter = make_counter()
    events = simulate(counter, [40, 58, 71, 89, 102])
    assert events == []
    assert counter.counts.entered == 0
    assert counter.counts.exited == 0


def test_stationary_person_at_edge_does_not_count() -> None:
    counter = make_counter()
    events = simulate(counter, [190] * 9)
    assert events == []
    assert counter.counts.entered == 0


def test_unconfirmed_track_cannot_count() -> None:
    counter = make_counter()
    for i, y in enumerate([40, 60, 80, 120, 160, 190], 1):
        track = observed_track(y)
        track = TrackedObject(
            track_id=track.track_id,
            bbox=track.bbox,
            confidence=track.confidence,
            camera_id=track.camera_id,
            state=TrackState.TENTATIVE,
        )
        assert counter.update(i, [track], (200, 200)) == []
    for frame_id in range(7, 12):
        assert counter.update(frame_id, [], (200, 200)) == []
