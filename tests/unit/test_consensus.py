from __future__ import annotations

from visitor_counter.configuration import ConsensusConfig
from visitor_counter.dual_camera_consensus import DualCameraConsensus
from visitor_counter.types import BoundingBox, CrossingEvent, Direction


def _event(camera_id: str, timestamp: float, area_scale: float = 1.0) -> CrossingEvent:
    return CrossingEvent(
        camera_id=camera_id,
        local_track_id=1,
        direction=Direction.IN,
        timestamp=timestamp,
        zone="entry",
        bbox=BoundingBox(0, 0, 100 * area_scale, 200 * area_scale),
        confidence=0.8,
    )


def test_duplicate_suppressed_inside_consensus_window() -> None:
    consensus = DualCameraConsensus(ConsensusConfig(expected_travel_seconds=1.0, transition_window_seconds=3.0))
    first = consensus.decide(_event("camera_1", 10.0))
    second = consensus.decide(_event("camera_2", 11.0))
    assert first.counted
    assert not second.counted
    assert second.duplicate_of is not None


def test_uncertain_event_marked_when_timing_is_late() -> None:
    consensus = DualCameraConsensus(
        ConsensusConfig(expected_travel_seconds=1.0, transition_window_seconds=1.0, uncertain_window_seconds=6.0)
    )
    consensus.decide(_event("camera_1", 10.0))
    decision = consensus.decide(_event("camera_2", 12.0, area_scale=1.0))
    assert decision.counted
    assert decision.uncertain
