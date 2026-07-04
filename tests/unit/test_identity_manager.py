from __future__ import annotations

from visitor_counter.configuration import IdentityConfig
from visitor_counter.identity_manager import GlobalIdentityManager
from visitor_counter.types import BoundingBox, TrackedObject


def _track(camera_id: str, track_id: int, box: BoundingBox) -> TrackedObject:
    return TrackedObject(track_id=track_id, bbox=box, confidence=0.9, camera_id=camera_id)


def test_same_person_visible_in_two_cameras_counts_once_globally() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.5))
    one = manager.update("camera_1", [_track("camera_1", 17, BoundingBox(100, 100, 300, 500))], 10.0, 1280, 720)
    two = manager.update("camera_2", [_track("camera_2", 4, BoundingBox(110, 105, 305, 510))], 10.2, 1280, 720)
    assert one[0].global_person_id == two[0].global_person_id
    assert manager.global_visible == 1


def test_two_different_people_in_two_cameras_count_as_two_visible() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.95))
    manager.update("camera_1", [_track("camera_1", 1, BoundingBox(100, 100, 250, 500))], 10.0, 1280, 720)
    manager.update("camera_2", [_track("camera_2", 2, BoundingBox(900, 40, 1220, 700))], 10.2, 1280, 720)
    assert manager.global_visible == 2


def test_new_local_track_id_can_keep_global_person_id() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.5, match_window_seconds=4.0))
    first = manager.update("camera_1", [_track("camera_1", 17, BoundingBox(100, 100, 300, 500))], 10.0, 1280, 720)[0]
    second = manager.update("camera_2", [_track("camera_2", 4, BoundingBox(105, 100, 302, 498))], 12.0, 1280, 720)[0]
    assert first.global_person_id == second.global_person_id
