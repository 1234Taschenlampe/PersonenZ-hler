"""Regression tests for mixed-direction passages and delayed edge confirmation."""
from __future__ import annotations

from visitor_counter.configuration import AppConfig, CameraConfig, TrackingConfig, validate_config
from visitor_counter.counter import LineCrossingCounter
from visitor_counter.types import BoundingBox, CountingLine, Direction, TrackedObject, TrackState


def track(frame: int, y: float, *, lost: int = 0, width: float = 40.0) -> TrackedObject:
    return TrackedObject(
        track_id=1,
        bbox=BoundingBox(75, y - 10, 75 + width, y + 10),
        confidence=0.96,
        camera_id="camera_1",
        lost_frames=lost,
        hits=frame,
        state=TrackState.CONFIRMED,
        global_person_id=7,
    )


def counter(*, role: str = "entrance", mode: str = "line", reverse: bool = False) -> LineCrossingCounter:
    camera = CameraConfig(
        camera_id="camera_1",
        role=role,
        width=200,
        height=200,
        entry_direction="B_to_A" if reverse else "A_to_B",
        exit_direction="A_to_B" if reverse else "B_to_A",
        counting_mode=mode,
        disappearance_frames=3,
        edge_margin_pixels=30,
    )
    tracking = TrackingConfig(
        min_stable_zone_frames=1,
        zone_hysteresis_pixels=0,
        min_confirmed_track_hits=2,
        minimum_bbox_area=0,
        minimum_confidence=0,
        count_cooldown_seconds=0,
        maximum_track_age=20,
    )
    return LineCrossingCounter(
        camera.camera_id, CountingLine((0, 100), (200, 100)), tracking, camera
    )


def test_entry_through_exit_and_exit_through_entrance() -> None:
    for role in ("entrance", "exit"):
        entering = counter(role=role)
        assert not entering.update(1, [track(1, 80)])
        events = entering.update(2, [track(2, 120)])
        assert [e.direction for e in events] == [Direction.IN]

        leaving = counter(role=role)
        leaving.update(1, [track(1, 120)])
        events = leaving.update(2, [track(2, 80)])
        assert [e.direction for e in events] == [Direction.OUT]


def test_reversed_camera_direction() -> None:
    c = counter(role="exit", reverse=True)
    c.update(1, [track(1, 120)])
    assert [event.direction for event in c.update(2, [track(2, 80)])] == [Direction.IN]


def test_line_scales_substream_640x360_to_configured_200x200() -> None:
    c = counter()
    c.update(1, [track(1, 80 * 0.5)], frame_size=(100, 100))
    events = c.update(2, [track(2, 120 * 0.5)], frame_size=(100, 100))
    assert [e.direction for e in events] == [Direction.IN]


def test_frame_edge_mode_requires_disappearance_after_real_transition() -> None:
    c = counter(mode="exit_edge")
    assert not c.update(1, [track(1, 80)])
    assert not c.update(2, [track(2, 120)])
    assert not c.update(3, [track(3, 195)])
    assert not c.update(4, [])
    assert not c.update(5, [])
    events = c.update(6, [])
    assert len(events) == 1
    assert events[0].direction == Direction.IN
    assert events[0].metadata["confirmed_at_exit_edge"] is True
    assert not c.update(7, [])


def test_edge_mode_refuses_mid_frame_disappearance() -> None:
    c = counter(mode="exit_edge")
    c.update(1, [track(1, 80)])
    c.update(2, [track(2, 120)])
    for frame in range(3, 9):
        assert c.update(frame, []) == []


def test_edge_mode_refuses_appearing_at_image_edge_without_crossing() -> None:
    c = counter(mode="exit_edge")
    c.update(1, [track(1, 195)])
    for frame in range(2, 8):
        assert c.update(frame, []) == []


def test_stale_tracker_boxes_do_not_confirm_crossings() -> None:
    c = counter()
    c.update(1, [track(1, 80)])
    assert not c.update(2, [track(2, 120, lost=1)])
    assert [e.direction for e in c.update(3, [track(3, 120)])] == [Direction.IN]


def test_both_default_cameras_accept_both_directions() -> None:
    c = AppConfig()
    assert validate_config(c) == []
    for camera in c.cameras.values():
        assert camera.entry_direction in ("A_to_B", "B_to_A")
        assert camera.exit_direction in ("A_to_B", "B_to_A")
        assert camera.entry_direction != camera.exit_direction
