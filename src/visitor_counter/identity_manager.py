from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import sqrt

from .configuration import IdentityConfig
from .types import BoundingBox, TrackedObject


@dataclass
class GlobalIdentityStats:
    global_visible: int = 0
    suppressed_matches: int = 0
    uncertain_matches: int = 0
    visible_global_ids: set[int] = field(default_factory=set)


@dataclass
class _GlobalProfile:
    global_person_id: int
    camera_id: str
    local_track_id: int
    bbox: BoundingBox
    normalized_center: tuple[float, float]
    normalized_area: float
    aspect_ratio: float
    first_seen: float
    last_seen: float
    visible: bool = True
    embedding: tuple[float, ...] | None = None


class GlobalIdentityManager:
    def __init__(self, config: IdentityConfig) -> None:
        self.config = config
        self._next_global_id = 1
        self._local_to_global: dict[tuple[str, int], int] = {}
        self._profiles: dict[int, _GlobalProfile] = {}
        self.stats = GlobalIdentityStats()

    def reset(self) -> None:
        self._next_global_id = 1
        self._local_to_global.clear()
        self._profiles.clear()
        self.stats = GlobalIdentityStats()

    def update(
        self,
        camera_id: str,
        tracks: list[TrackedObject],
        timestamp: float,
        frame_width: int,
        frame_height: int,
    ) -> list[TrackedObject]:
        self._expire(timestamp)
        visible_global_ids: set[int] = set()
        assigned: list[TrackedObject] = []
        for track in tracks:
            if track.lost_frames != 0:
                assigned.append(track)
                continue
            key = (camera_id, track.track_id)
            global_id = self._local_to_global.get(key)
            if global_id is None:
                global_id = self._match_existing(camera_id, track, timestamp, frame_width, frame_height)
                if global_id is None:
                    global_id = self._allocate_global_id()
                else:
                    self.stats.suppressed_matches += 1
                self._local_to_global[key] = global_id
            self._profiles[global_id] = self._profile(global_id, camera_id, track, timestamp, frame_width, frame_height)
            visible_global_ids.add(global_id)
            assigned.append(replace(track, global_person_id=global_id))
        visible = self._visible_ids(timestamp) | visible_global_ids
        self.stats.global_visible = len(visible)
        self.stats.visible_global_ids = visible
        return assigned

    @property
    def global_visible(self) -> int:
        return self.stats.global_visible

    @property
    def visible_global_ids(self) -> set[int]:
        return set(self.stats.visible_global_ids or set())

    def _allocate_global_id(self) -> int:
        value = self._next_global_id
        self._next_global_id += 1
        return value

    def _match_existing(
        self,
        camera_id: str,
        track: TrackedObject,
        timestamp: float,
        frame_width: int,
        frame_height: int,
    ) -> int | None:
        candidate = self._profile(0, camera_id, track, timestamp, frame_width, frame_height)
        best_id: int | None = None
        best_score = -1.0
        for global_id, profile in self._profiles.items():
            if profile.camera_id == camera_id:
                continue
            age = timestamp - profile.last_seen
            if age < 0 or age > self.config.match_window_seconds:
                continue
            score = self._score(profile, candidate, age)
            if score > best_score:
                best_id = global_id
                best_score = score
        if best_id is not None and best_score >= self.config.reid_threshold:
            return best_id
        if best_id is not None and best_score >= self.config.reid_threshold * 0.75:
            self.stats.uncertain_matches += 1
        return None

    def _profile(
        self,
        global_id: int,
        camera_id: str,
        track: TrackedObject,
        timestamp: float,
        frame_width: int,
        frame_height: int,
    ) -> _GlobalProfile:
        box = track.bbox
        cx, cy = box.center
        normalized_area = box.area / max(float(frame_width * frame_height), 1.0)
        aspect_ratio = box.width / max(box.height, 1.0)
        return _GlobalProfile(
            global_person_id=global_id,
            camera_id=camera_id,
            local_track_id=track.track_id,
            bbox=box,
            normalized_center=(cx / max(frame_width, 1), cy / max(frame_height, 1)),
            normalized_area=normalized_area,
            aspect_ratio=aspect_ratio,
            first_seen=timestamp,
            last_seen=timestamp,
            visible=True,
            embedding=track.embedding,
        )

    def _score(self, first: _GlobalProfile, second: _GlobalProfile, age: float) -> float:
        area_delta = abs(first.normalized_area - second.normalized_area) / max(first.normalized_area, second.normalized_area, 0.001)
        aspect_delta = abs(first.aspect_ratio - second.aspect_ratio) / max(first.aspect_ratio, second.aspect_ratio, 0.001)
        dx = first.normalized_center[0] - second.normalized_center[0]
        dy = first.normalized_center[1] - second.normalized_center[1]
        position_distance = sqrt((dx * dx) + (dy * dy))
        age_score = max(0.0, 1.0 - (age / max(self.config.match_window_seconds, 0.001)))
        shape_score = max(0.0, 1.0 - ((area_delta * 0.65) + (aspect_delta * 0.35)))
        position_score = max(0.0, 1.0 - position_distance)
        base_score = (shape_score * 0.45) + (position_score * 0.20) + (age_score * 0.20)
        if first.embedding is None or second.embedding is None:
            return base_score + (shape_score * 0.15)
        reid_score = max(0.0, min(1.0, _cosine_similarity(first.embedding, second.embedding)))
        return base_score + (reid_score * 0.15)

    def _visible_ids(self, timestamp: float) -> set[int]:
        return {
            global_id
            for global_id, profile in self._profiles.items()
            if timestamp - profile.last_seen <= self.config.stale_seconds
        }

    def _expire(self, timestamp: float) -> None:
        max_age = min(max(self.config.match_window_seconds, self.config.stale_seconds) * 3.0, self.config.cache_ttl_seconds)
        stale_ids = [global_id for global_id, profile in self._profiles.items() if timestamp - profile.last_seen > max_age]
        for global_id in stale_ids:
            del self._profiles[global_id]
        stale_local = [key for key, global_id in self._local_to_global.items() if global_id not in self._profiles]
        for key in stale_local:
            del self._local_to_global[key]


def _cosine_similarity(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    if len(first) != len(second) or not first:
        return 0.0
    return sum(a * b for a, b in zip(first, second))
