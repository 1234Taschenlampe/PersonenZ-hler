from __future__ import annotations

from dataclasses import dataclass, field
import logging
from time import time

from .types import CountingLine, CrossingEvent, Direction, TrackedObject
from .configuration import TrackingConfig, CameraConfig

LOGGER = logging.getLogger(__name__)


@dataclass
class LocalCounts:
    inside: int = 0
    entered: int = 0
    exited: int = 0
    visible: int = 0


@dataclass
class _TrackMemory:
    first_seen_frame: int
    last_seen_frame: int
    raw_zone_history: list[str] = field(default_factory=list)
    stable_zone: str = "neutral"
    stable_zone_history: list[str] = field(default_factory=list)
    counted: bool = False
    last_count_time: float = 0.0
    previous_center: tuple[float, float] | None = None


class LineCrossingCounter:
    def __init__(self, camera_id: str, line: CountingLine, tracking_config: TrackingConfig, camera_config: CameraConfig) -> None:
        self.camera_id = camera_id
        self.line = line
        self.tracking_config = tracking_config
        self.camera_config = camera_config
        self.counts = LocalCounts()
        self._tracks: dict[int, _TrackMemory] = {}
        
        # Precompute line details
        ax, ay = self.line.start
        bx, by = self.line.end
        self.line_length = max(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 1.0)
        self.normal_vector = (-(by - ay) / self.line_length, (bx - ax) / self.line_length)

    def reset(self) -> None:
        self.counts = LocalCounts()
        self._tracks.clear()
        LOGGER.info("Counter reset for %s", self.camera_id)

    def update(self, frame_id: int, tracks: list[TrackedObject]) -> list[CrossingEvent]:
        events: list[CrossingEvent] = []
        self.counts.visible = len({track.track_id for track in tracks if track.lost_frames == 0 and track.confirmed})
        camera_num = 1 if self.camera_id == "camera_1" else 2
        
        for track in tracks:
            # Check bounding box validity and area first
            if track.bbox.width <= 1 or track.bbox.height <= 1:
                LOGGER.debug("COUNT_REJECTED camera=%s reason=invalid_bbox", camera_num)
                continue
            
            area = track.bbox.area
            if area < self.tracking_config.minimum_bbox_area:
                LOGGER.debug("COUNT_REJECTED camera=%s reason=outside_counting_area", camera_num)
                continue

            # Compute anchor (use center for stability as requested)
            anchor = track.bbox.center
            
            # Compute distance in pixels to line
            side = self.line.side(anchor)
            distance = side / self.line_length
            
            # Determine raw zone
            hysteresis = self.tracking_config.zone_hysteresis_pixels
            if distance < -hysteresis:
                raw_zone = "A"
            elif distance > hysteresis:
                raw_zone = "B"
            else:
                raw_zone = "neutral"

            memory = self._tracks.get(track.track_id)
            is_new = memory is None
            if is_new:
                memory = _TrackMemory(
                    first_seen_frame=frame_id,
                    last_seen_frame=frame_id,
                    raw_zone_history=[],
                    stable_zone="neutral",
                    stable_zone_history=["neutral"],
                    previous_center=anchor
                )
                self._tracks[track.track_id] = memory
                LOGGER.debug("TRACK camera=%s confirmed=%s state=new", camera_num, track.confirmed)
            else:
                LOGGER.debug("TRACK camera=%s confirmed=%s state=active", camera_num, track.confirmed)

            memory.previous_center = anchor
            memory.last_seen_frame = frame_id
            
            # Update raw zone history
            memory.raw_zone_history.append(raw_zone)
            limit = self.tracking_config.min_stable_zone_frames
            if len(memory.raw_zone_history) > limit:
                memory.raw_zone_history.pop(0)

            # Determine stable zone
            if len(memory.raw_zone_history) >= limit and len(set(memory.raw_zone_history)) == 1:
                new_stable = memory.raw_zone_history[0]
                if new_stable != memory.stable_zone:
                    LOGGER.debug(
                        "ZONE_STATE camera=%s previous_zone=%s current_zone=%s stable_frames=%s",
                        camera_num, memory.stable_zone, new_stable, limit,
                    )
                    memory.stable_zone = new_stable
                    if not memory.stable_zone_history or memory.stable_zone_history[-1] != new_stable:
                        memory.stable_zone_history.append(new_stable)
                        # Process potential transition
                        events.extend(self._process_transition(track, memory, frame_id))
            else:
                # No stable zone change this frame
                LOGGER.debug("COUNT_REJECTED camera=%s reason=no_zone_change", camera_num)

        # Cleanup expired tracks
        for track_id in list(self._tracks.keys()):
            if frame_id - self._tracks[track_id].last_seen_frame > self.tracking_config.maximum_track_age:
                del self._tracks[track_id]

        return events

    def _process_transition(self, track: TrackedObject, memory: _TrackMemory, frame_id: int) -> list[CrossingEvent]:
        # We need at least two stable zones to see a transition
        if len(memory.stable_zone_history) < 2:
            return []
        
        # Find the last non-neutral stable zone before current
        current_stable = memory.stable_zone
        if current_stable == "neutral":
            return []
            
        prev_non_neutral = None
        for z in reversed(memory.stable_zone_history[:-1]):
            if z in ("A", "B"):
                prev_non_neutral = z
                break
                
        if not prev_non_neutral or prev_non_neutral == current_stable:
            return []
            
        # We have a transition! Either A -> B or B -> A
        transition = f"{prev_non_neutral}_to_{current_stable}"
        
        # Determine direction
        direction = Direction.UNKNOWN
        if transition == self.camera_config.entry_direction:
            direction = Direction.IN
        elif transition == self.camera_config.exit_direction:
            direction = Direction.OUT

        # Validate count constraints and log rejections if any fail
        camera_num = 1 if self.camera_id == "camera_1" else 2
        if direction == Direction.UNKNOWN:
            LOGGER.info("COUNT_REJECTED camera=%s reason=wrong_direction", camera_num)
            return []
            
        if not track.confirmed:
            LOGGER.info("COUNT_REJECTED camera=%s reason=track_not_confirmed", camera_num)
            return []
            
        hits = frame_id - memory.first_seen_frame + 1
        if hits < self.tracking_config.min_confirmed_track_hits:
            LOGGER.info("COUNT_REJECTED camera=%s reason=insufficient_history", camera_num)
            return []
            
        if memory.counted:
            LOGGER.info("COUNT_REJECTED camera=%s reason=already_counted", camera_num)
            return []
            
        now = time()
        if now - memory.last_count_time < self.tracking_config.count_cooldown_seconds:
            LOGGER.info("COUNT_REJECTED camera=%s reason=cooldown_active", camera_num)
            return []
            
        if track.confidence < self.tracking_config.minimum_confidence:
            LOGGER.info("COUNT_REJECTED camera=%s reason=confidence_too_low", camera_num)
            return []

        # All checks passed! Count it
        memory.counted = True
        memory.last_count_time = now

        if direction == Direction.IN:
            self.counts.entered += 1
            self.counts.inside += 1
            zone_label = "entry"
        else:
            self.counts.exited += 1
            self.counts.inside = max(0, self.counts.inside - 1)
            zone_label = "exit"

        passage_id = f"{track.global_person_id or 'local'}:{self.camera_id}:{direction.value}:{frame_id}"
        event = CrossingEvent(
            camera_id=self.camera_id,
            local_track_id=track.track_id,
            global_person_id=track.global_person_id,
            passage_id=passage_id,
            direction=direction,
            timestamp=now,
            zone=zone_label,
            bbox=track.bbox,
            confidence=track.confidence,
            metadata={
                "frame_id": frame_id,
                "line": (self.line.start, self.line.end),
                "camera_role": self.camera_config.role,
                "transition": transition,
                "anchor": track.bbox.center,
                "zones": list(memory.stable_zone_history),
            },
        )
        
        return [event]


@dataclass
class GlobalCounts:
    inside: int = 0
    entered: int = 0
    exited: int = 0
    visible: int = 0
    suppressed_duplicates: int = 0
    uncertain_consensus: int = 0
    timeouts: int = 0

    def apply(self, direction: Direction, counted: bool, uncertain: bool) -> None:
        if not counted:
            self.suppressed_duplicates += 1
            return
        if uncertain:
            self.uncertain_consensus += 1
            return
        if direction is Direction.IN:
            self.entered += 1
            self.inside += 1
        elif direction is Direction.OUT:
            self.exited += 1
            self.inside = max(0, self.inside - 1)
