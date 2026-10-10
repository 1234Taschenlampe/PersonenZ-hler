from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import time

from .configuration import CameraConfig, TrackingConfig
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
    first_seen_frame: int
    last_seen_frame: int
    raw_zone_history: list[str] = field(default_factory=list)
    stable_zone: str = "neutral"
    stable_zone_history: list[str] = field(default_factory=list)
    counted: bool = False
    last_count_time: float = 0.0
    previous_center: tuple[float, float] | None = None
    initial_side: str | None = None
    last_confirmed_track: TrackedObject | None = None
    last_near_edge: bool = False
    observed_frames: int = 0
    zone_revision: int = 0
    counted_zone_revision: int = -1
    # Recent center points in the configured reference coordinate system.
    # Edge exits are classified by observed travel, not a synthetic midline.
    observed_positions: list[tuple[float, float]] = field(default_factory=list)
    exit_edge_side: str | None = None
    edge_exit_checked: bool = False


class LineCrossingCounter:
    def __init__(
        self,
        camera_id: str,
        line: CountingLine,
        tracking_config: TrackingConfig,
        camera_config: CameraConfig,
    ) -> None:
        self.camera_id = camera_id
        self.line = line
        self.tracking_config = tracking_config
        self.camera_config = camera_config
        self.counts = LocalCounts()
        self._tracks: dict[int, _TrackMemory] = {}
        self.rejected_events = 0
        self.last_rejection_reason = ""
        self.rejection_counts: dict[str, int] = {}

        # Precompute line details
        ax, ay = self.line.start
        bx, by = self.line.end
        self.line_length = max(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5, 1.0)
        self.normal_vector = (
            -(by - ay) / self.line_length,
            (bx - ax) / self.line_length,
        )

    def reset(self) -> None:
        self.counts = LocalCounts()
        self._tracks.clear()
        self.rejected_events = 0
        self.last_rejection_reason = ""
        self.rejection_counts.clear()
        LOGGER.info("Counter reset for %s", self.camera_id)

    def _reject(self, reason: str) -> None:
        self.rejected_events += 1
        self.last_rejection_reason = reason
        self.rejection_counts[reason] = self.rejection_counts.get(reason, 0) + 1
        LOGGER.debug("COUNT_REJECTED camera=%s reason=%s", self.camera_id, reason)

    def update(
        self, frame_id: int, tracks: list[TrackedObject],
        frame_size: tuple[int, int] | None = None,
    ) -> list[CrossingEvent]:
        events: list[CrossingEvent] = []
        self.counts.visible = len(
            {
                track.track_id
                for track in tracks
                if track.lost_frames == 0 and track.confirmed
            }
        )
        camera_num = 1 if self.camera_id == "camera_1" else 2
        frame_width, frame_height = frame_size or (
            self.camera_config.width, self.camera_config.height
        )
        if frame_width <= 0 or frame_height <= 0:
            return []

        for track in tracks:
            # The tracker returns stale boxes while a person is temporarily
            # occluded. Never treat these coordinates as real observations.
            if track.lost_frames > 0:
                continue
            # Check bounding box validity and area first
            if track.bbox.width <= 1 or track.bbox.height <= 1:
                self._reject("invalid_bbox")
                continue

            area = track.bbox.area
            if area < self.tracking_config.minimum_bbox_area:
                self._reject("bbox_too_small")
                continue

            # Compute anchor (use center for stability as requested)
            anchor = track.bbox.center

            # Compute distance in pixels to line
            # Camera configuration uses reference dimensions (usually 1280x720),
            # while Reolink's substream may be 640x360 or 640x480.
            # Normalize into the configured counting-line coordinate system.
            point = (
                anchor[0] * self.camera_config.width / frame_width,
                anchor[1] * self.camera_config.height / frame_height,
            )
            side = self.line.side(point)
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
                    previous_center=anchor,
                )
                self._tracks[track.track_id] = memory
                LOGGER.debug(
                    "TRACK camera=%s confirmed=%s state=new",
                    camera_num,
                    track.confirmed,
                )
            else:
                LOGGER.debug(
                    "TRACK camera=%s confirmed=%s state=active",
                    camera_num,
                    track.confirmed,
                )

            memory.previous_center = anchor
            memory.observed_positions.append(point)
            memory.observed_positions = memory.observed_positions[-24:]
            memory.last_seen_frame = frame_id
            memory.observed_frames += 1
            if track.confirmed:
                memory.last_confirmed_track = track
            margin = max(
                8.0,
                self.camera_config.edge_margin_pixels * min(
                    frame_width / max(1, self.camera_config.width),
                    frame_height / max(1, self.camera_config.height),
                ),
            )
            edge_contact = max(8.0, margin * 0.12)
            # Only boundaries perpendicular to the selected travel axis
            # can generate events (top/bottom for a horizontal reference line).
            # Require actual box contact, and a center close to that edge.
            # An arbitrary side-edge occlusion must not be counted as passage.
            nx, ny = self.normal_vector
            if abs(ny) >= abs(nx):
                edge_side = (
                    "B" if ny > 0 else "A"
                ) if (
                    anchor[1] >= frame_height - margin - track.bbox.height / 2
                    and track.bbox.y2 >= frame_height - edge_contact
                ) else (
                    ("A" if ny > 0 else "B")
                    if (anchor[1] <= margin + track.bbox.height / 2
                        and track.bbox.y1 <= edge_contact) else None
                )
            else:
                edge_side = (
                    "B" if nx > 0 else "A"
                ) if (
                    anchor[0] >= frame_width - margin - track.bbox.width / 2
                    and track.bbox.x2 >= frame_width - edge_contact
                ) else (
                    ("A" if nx > 0 else "B")
                    if (anchor[0] <= margin + track.bbox.width / 2
                        and track.bbox.x1 <= edge_contact) else None
                )
            memory.exit_edge_side = edge_side
            memory.last_near_edge = edge_side is not None

            # Update raw zone history
            memory.raw_zone_history.append(raw_zone)
            limit = self.tracking_config.min_stable_zone_frames
            if len(memory.raw_zone_history) > limit:
                memory.raw_zone_history.pop(0)

            # Determine stable zone
            if (
                len(memory.raw_zone_history) >= limit
                and len(set(memory.raw_zone_history)) == 1
            ):
                new_stable = memory.raw_zone_history[0]
                if new_stable != memory.stable_zone:
                    LOGGER.debug(
                        "ZONE_STATE camera=%s previous_zone=%s current_zone=%s stable_frames=%s",
                        camera_num,
                        memory.stable_zone,
                        new_stable,
                        limit,
                    )
                    memory.stable_zone = new_stable
                    if new_stable in ("A", "B") and memory.initial_side is None:
                        memory.initial_side = new_stable
                    if (
                        not memory.stable_zone_history
                        or memory.stable_zone_history[-1] != new_stable
                    ):
                        memory.stable_zone_history.append(new_stable)
                        memory.zone_revision += 1
                        # Only the latest transition is needed. Bound memory
                        # for people who remain visible for a long time.
                        memory.stable_zone_history = memory.stable_zone_history[-12:]
            else:
                # No stable zone change this frame
                LOGGER.debug(
                    "COUNT_REJECTED camera=%s reason=no_zone_change", camera_num
                )

            # A real crossing can precede track confirmation. Retain it until
            # confirmation instead of requiring another zone change to count.
            if self.camera_config.counting_mode == "line":
                events.extend(self._process_transition(track, memory, frame_id))

        # Confirm a passage at disappearance only when the person has a
        # verified A->B/B->A transition AND was last seen near a real image
        # boundary. Mid-frame occlusions and temporary tracker loss never count.
        visible_ids = {track.track_id for track in tracks if track.lost_frames == 0}
        for track_id, memory in list(self._tracks.items()):
            missing_frames = frame_id - memory.last_seen_frame
            if (
                self.camera_config.counting_mode == "exit_edge"
                and track_id not in visible_ids
                and missing_frames >= self.camera_config.disappearance_frames
                and not memory.counted
                and not memory.edge_exit_checked
                and memory.last_near_edge
                and memory.last_confirmed_track is not None
            ):
                memory.edge_exit_checked = True
                transition = self._edge_exit_transition(memory)
                if transition:
                    events.extend(
                        self._process_transition(
                            memory.last_confirmed_track, memory, frame_id,
                            on_disappearance=True, forced_transition=transition,
                        )
                    )
                else:
                    self._reject("edge_exit_without_confirmed_travel")
            if missing_frames > self.tracking_config.maximum_track_age:
                del self._tracks[track_id]

        return events

    def _edge_exit_transition(self, memory: _TrackMemory) -> str | None:
        """Infer departure direction using measured motion toward a real edge.

        Do not infer entry/exit merely from vanishing in the image.
        A confirmed person must approach the matching directional boundary
        over multiple observed frames. Only one event may be emitted per track.
        """
        points = memory.observed_positions
        if len(points) < max(3, self.tracking_config.min_confirmed_track_hits):
            return None
        if memory.exit_edge_side not in {"A", "B"}:
            return None
        nx, ny = self.normal_vector
        projections = [x * nx + y * ny for x, y in points]
        # The first and last positions are compared over a bounded window.
        movement = projections[-1] - projections[0]
        reference_axis = (
            self.camera_config.height if abs(ny) >= abs(nx)
            else self.camera_config.width
        )
        minimum_travel = max(25.0, reference_axis * 0.06)
        if abs(movement) < minimum_travel:
            return None
        # A short reverse move at the boundary invalidates the departure.
        tail = projections[-min(4, len(projections)):]
        recent_travel = tail[-1] - tail[0]
        if recent_travel * movement < -max(8.0, minimum_travel * 0.25):
            return None
        destination = "B" if movement > 0 else "A"
        if destination != memory.exit_edge_side:
            return None
        return "A_to_B" if destination == "B" else "B_to_A"

    def _process_transition(
        self, track: TrackedObject, memory: _TrackMemory, frame_id: int,
        *, on_disappearance: bool = False, forced_transition: str | None = None,
    ) -> list[CrossingEvent]:
        if forced_transition is None:
            # Line mode still requires an actual stable zone transition.
            if len(memory.stable_zone_history) < 2:
                return []
            current_stable = memory.stable_zone
            if current_stable == "neutral":
                return []
            prev_non_neutral = next(
                (z for z in reversed(memory.stable_zone_history[:-1])
                 if z in ("A", "B")), None
            )
            if not prev_non_neutral or prev_non_neutral == current_stable:
                return []
            transition = f"{prev_non_neutral}_to_{current_stable}"
        else:
            transition = forced_transition

        if memory.counted_zone_revision == memory.zone_revision and forced_transition is None:
            return []
        if on_disappearance and (memory.counted or not memory.last_near_edge):
            return []

        # Determine direction
        direction = Direction.UNKNOWN
        if transition == self.camera_config.entry_direction:
            direction = Direction.IN
        elif transition == self.camera_config.exit_direction:
            direction = Direction.OUT

        # Validate count constraints and log rejections if any fail
        if not track.confirmed:
            self._reject("track_not_confirmed")
            return []

        # Capture IDs may skip arbitrarily many frames when queues drop old
        # images. Only genuine observations establish counting history.
        hits = memory.observed_frames
        if hits < self.tracking_config.min_confirmed_track_hits:
            self._reject("insufficient_history")
            return []

        now = time()
        if now - memory.last_count_time < self.tracking_config.count_cooldown_seconds:
            self._reject("cooldown_active")
            return []

        if track.confidence < self.tracking_config.minimum_confidence:
            self._reject("confidence_too_low")
            return []

        # All checks passed! Count it
        memory.counted = True
        memory.counted_zone_revision = memory.zone_revision
        memory.last_count_time = now

        if direction == Direction.IN:
            self.counts.entered += 1
            self.counts.inside += 1
            zone_label = "entry"
        elif direction == Direction.OUT:
            self.counts.exited += 1
            self.counts.inside = max(0, self.counts.inside - 1)
            zone_label = "exit"
        else:
            # An otherwise valid transition which is not configured as entry or
            # exit is a useful safety event. It must not alter occupancy.
            zone_label = "wrong_way"

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
                "counting_mode": self.camera_config.counting_mode,
                "confirmed_at_exit_edge": on_disappearance,
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
    daily_unique: int = 0
    daily_unique_degraded: bool = True
    wrong_way: int = 0

    @property
    def throughput(self) -> int:
        return self.entered + self.exited

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
        else:
            self.wrong_way += 1
