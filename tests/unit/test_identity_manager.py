from __future__ import annotations

from visitor_counter.configuration import IdentityConfig
from visitor_counter.identity_manager import GlobalIdentityManager
from visitor_counter.types import BoundingBox, TrackState, TrackedObject


def _track(camera_id: str, track_id: int, box: BoundingBox, embedding: tuple[float, ...] | None = None) -> TrackedObject:
    return TrackedObject(
        track_id=track_id,
        bbox=box,
        confidence=0.9,
        camera_id=camera_id,
        state=TrackState.CONFIRMED,
        embedding=embedding,
    )


def test_same_person_visible_in_two_cameras_counts_once_globally() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.62))
    emb = (1.0, 0.0, 0.0, 0.0)
    one = manager.update("camera_1", [_track("camera_1", 17, BoundingBox(100, 100, 300, 500), emb)], 10.0, 1280, 720)
    two = manager.update("camera_2", [_track("camera_2", 4, BoundingBox(110, 105, 305, 510), emb)], 10.2, 1280, 720)
    assert one[0].global_person_id == two[0].global_person_id
    assert manager.global_visible == 1


def test_two_different_people_in_two_cameras_count_as_two_visible() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.62))
    manager.update("camera_1", [_track("camera_1", 1, BoundingBox(100, 100, 250, 500), (1.0, 0.0, 0.0, 0.0))], 10.0, 1280, 720)
    manager.update("camera_2", [_track("camera_2", 2, BoundingBox(900, 40, 1220, 700), (0.0, 1.0, 0.0, 0.0))], 10.2, 1280, 720)
    assert manager.global_visible == 2


def test_geometry_without_embedding_is_not_enough_for_cross_camera_match() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.62))
    one = manager.update("camera_1", [_track("camera_1", 17, BoundingBox(100, 100, 300, 500))], 10.0, 1280, 720)
    two = manager.update("camera_2", [_track("camera_2", 4, BoundingBox(105, 100, 302, 498))], 10.2, 1280, 720)
    assert one[0].global_person_id != two[0].global_person_id


def test_new_local_track_id_can_keep_global_person_id_with_reid() -> None:
    manager = GlobalIdentityManager(IdentityConfig(reid_threshold=0.62, match_window_seconds=4.0))
    emb = (0.8, 0.6, 0.0, 0.0)
    first = manager.update("camera_1", [_track("camera_1", 17, BoundingBox(100, 100, 300, 500), emb)], 10.0, 1280, 720)[0]
    second = manager.update("camera_2", [_track("camera_2", 4, BoundingBox(105, 100, 302, 498), emb)], 12.0, 1280, 720)[0]
    assert first.global_person_id == second.global_person_id
