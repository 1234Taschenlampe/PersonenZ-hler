from __future__ import annotations

from dataclasses import dataclass
import logging

from .configuration import TrackingConfig
from .types import BoundingBox, Detection, TrackedObject, TrackState

LOGGER = logging.getLogger(__name__)


def bbox_iou(a: BoundingBox, b: BoundingBox) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a.area + b.area - inter
    return 0.0 if union <= 0 else inter / union


@dataclass
class _Track:
    track_id: int
    bbox: BoundingBox
    confidence: float
    age_frames: int = 1
    hits: int = 1
    lost_frames: int = 0
    state: TrackState = TrackState.TENTATIVE


class Tracker:
    def update(self, camera_id: str, detections: list[Detection]) -> list[TrackedObject]:
        raise NotImplementedError


class IoUFallbackTracker(Tracker):
    """Deterministic one-to-one IoU tracker with explicit track states."""

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config
        self._next_id = 1
        self._tracks: dict[int, _Track] = {}

    def update(self, camera_id: str, detections: list[Detection]) -> list[TrackedObject]:
        unmatched_indices = set(range(len(detections)))
        for track in self._tracks.values():
            track.lost_frames += 1

        matches: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            for detection_index in unmatched_indices:
                score = bbox_iou(track.bbox, detections[detection_index].bbox)
                if score >= self.config.iou_match_threshold:
                    matches.append((score, track_id, detection_index))

        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        for _score, track_id, detection_index in sorted(matches, reverse=True):
            if track_id in used_tracks or detection_index in used_detections:
                continue
            detection = detections[detection_index]
            track = self._tracks[track_id]
            track.bbox = detection.bbox
            track.confidence = detection.confidence
            track.age_frames += 1
            track.hits += 1
            track.lost_frames = 0
            track.state = TrackState.CONFIRMED if track.hits >= self.config.min_confirmed_hits else TrackState.TENTATIVE
            used_tracks.add(track_id)
            used_detections.add(detection_index)

        for detection_index in unmatched_indices - used_detections:
            detection = detections[detection_index]
            self._tracks[self._next_id] = _Track(self._next_id, detection.bbox, detection.confidence)
            self._next_id += 1

        for track_id, track in list(self._tracks.items()):
            if track.lost_frames > self.config.max_lost_frames:
                del self._tracks[track_id]
            elif track.lost_frames > 0 and track.state is TrackState.CONFIRMED:
                track.state = TrackState.OCCLUDED
            elif track.lost_frames > 0:
                track.state = TrackState.LOST

        return [
            TrackedObject(
                track_id=track.track_id,
                bbox=track.bbox,
                confidence=track.confidence,
                camera_id=camera_id,
                age_frames=track.age_frames,
                lost_frames=track.lost_frames,
                hits=track.hits,
                state=track.state,
            )
            for track in self._tracks.values()
        ]


def create_tracker(config: TrackingConfig) -> tuple[Tracker, str]:
    try:
        import ultralytics  # noqa: F401

        LOGGER.warning("Ultralytics is installed, but the embedded fallback tracker is active until ByteTrack wiring is configured.")
    except ImportError:
        LOGGER.warning("ByteTrack dependency not installed; using IoU fallback tracker.")
    return IoUFallbackTracker(config), "IoU fallback tracker"
