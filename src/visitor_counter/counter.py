from __future__ import annotations

from dataclasses import dataclass, field
import logging
from time import time

from .types import CountingLine, CrossingEvent, Direction, TrackedObject

LOGGER = logging.getLogger(__name__)


@dataclass
class LocalCounts:
    inside: int = 0
    entered: int = 0
    exited: int = 0
    visible: int = 0


@dataclass
class _TrackMemory:
    last_side: float
    first_seen_frame: int
    last_seen_frame: int
    zones: list[str] = field(default_factory=list)
    counted_crossings: set[tuple[str, int, str]] = field(default_factory=set)


class LineCrossingCounter:
    def __init__(self, camera_id: str, line: CountingLine, min_hits_before_counting: int = 2, role: str = "entrance") -> None:
        self.camera_id = camera_id
        self.line = line
        self.min_hits_before_counting = min_hits_before_counting
        self.role = role
        self.counts = LocalCounts()
        self._tracks: dict[int, _TrackMemory] = {}

    def reset(self) -> None:
        self.counts = LocalCounts()
        self._tracks.clear()
        LOGGER.info("Counter reset for %s", self.camera_id)

    def update(self, frame_id: int, tracks: list[TrackedObject]) -> list[CrossingEvent]:
        events: list[CrossingEvent] = []
        self.counts.visible = len({track.track_id for track in tracks if track.lost_frames == 0 and track.confirmed})
        for track in tracks:
            anchor = ((track.bbox.x1 + track.bbox.x2) / 2.0, track.bbox.y2)
            side = self.line.side(anchor)
            zone = self._zone_for_side(side)
            memory = self._tracks.get(track.track_id)
            if memory is None:
                self._tracks[track.track_id] = _TrackMemory(side, frame_id, frame_id, [zone])
                continue
            hits = frame_id - memory.first_seen_frame + 1
            memory.zones.append(zone)
            memory.zones = memory.zones[-12:]
            crossed = (memory.last_side < 0 <= side) or (memory.last_side > 0 >= side)
            direction = self._direction_for_crossing(memory.last_side, side)
            crossing_key = (self.camera_id, track.track_id, direction.value)
            has_confirmed_track = track.confirmed or track.hits >= self.min_hits_before_counting or hits >= self.min_hits_before_counting
            has_directed_passage = self._has_directed_passage(memory.zones, direction)
            if (
                crossed
                and has_confirmed_track
                and has_directed_passage
                and crossing_key not in memory.counted_crossings
            ):
                expected = Direction.IN if self.role == "entrance" else Direction.OUT
                valid_for_role = direction is expected
                if valid_for_role and direction is Direction.IN:
                    self.counts.entered += 1
                    self.counts.inside += 1
                    zone = "entry"
                elif valid_for_role and direction is Direction.OUT:
                    self.counts.exited += 1
                    self.counts.inside = max(0, self.counts.inside - 1)
                    zone = "exit"
                else:
                    zone = "wrong_direction"
                passage_id = f"{track.global_person_id or 'local'}:{self.camera_id}:{direction.value}:{frame_id}"
                event = CrossingEvent(
                    camera_id=self.camera_id,
                    local_track_id=track.track_id,
                    global_person_id=track.global_person_id,
                    passage_id=passage_id,
                    direction=direction,
                    timestamp=time(),
                    zone=zone,
                    bbox=track.bbox,
                    confidence=track.confidence,
                    metadata={
                        "frame_id": frame_id,
                        "line": (self.line.start, self.line.end),
                        "camera_role": self.role,
                        "valid_for_role": valid_for_role,
                        "anchor": anchor,
                        "zones": list(memory.zones),
                    },
                )
                events.append(event)
                memory.counted_crossings.add(crossing_key)
                LOGGER.info(
                    "Crossing event camera=%s role=%s track=%s global=%s direction=%s valid=%s",
                    self.camera_id,
                    self.role,
                    track.track_id,
                    track.global_person_id,
                    direction.value,
                    valid_for_role,
                )
            memory.last_side = side
            memory.last_seen_frame = frame_id
        return events

    def _direction_for_crossing(self, previous_side: float, current_side: float) -> Direction:
        moved_to_positive = previous_side < current_side
        if moved_to_positive == self.line.in_positive_side:
            return Direction.IN
        return Direction.OUT

    def _zone_for_side(self, side: float) -> str:
        ax, ay = self.line.start
        bx, by = self.line.end
        line_length = max(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 1.0)
        band = line_length * 5.0
        if abs(side) <= band:
            return "transition"
        positive_is_inside = self.line.in_positive_side
        is_positive = side > 0
        return "inside" if is_positive == positive_is_inside else "outside"

    def _has_directed_passage(self, zones: list[str], direction: Direction) -> bool:
        compact: list[str] = []
        for zone in zones:
            if not compact or compact[-1] != zone:
                compact.append(zone)
        sequence = ["outside", "transition", "inside"] if direction is Direction.IN else ["inside", "transition", "outside"]
        position = 0
        for zone in compact:
            if zone == sequence[position]:
                position += 1
                if position == len(sequence):
                    return True
        if len(compact) >= 2:
            return compact[0] == sequence[0] and compact[-1] == sequence[-1]
        return False


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
