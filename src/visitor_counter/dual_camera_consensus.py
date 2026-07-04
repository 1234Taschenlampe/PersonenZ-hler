from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging

from .configuration import ConsensusConfig
from .types import ConsensusDecision, CrossingEvent

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CandidateMatch:
    event: CrossingEvent
    score: float
    reason: str


class DualCameraConsensus:
    def __init__(self, config: ConsensusConfig) -> None:
        self.config = config
        self._recent: deque[CrossingEvent] = deque(maxlen=200)

    def reset(self) -> None:
        self._recent.clear()

    def decide(self, event: CrossingEvent) -> ConsensusDecision:
        if not self.config.enabled:
            self._recent.append(event)
            return ConsensusDecision(event=event, counted=True, duplicate_of=None, uncertain=False, reason="consensus disabled")

        self._drop_expired(event.timestamp)
        match = self._best_match(event)
        self._recent.append(event)
        if match and match.score >= 0.75:
            LOGGER.info(
                "Suppressed duplicate camera=%s track=%s matched_camera=%s score=%.2f",
                event.camera_id,
                event.local_track_id,
                match.event.camera_id,
                match.score,
            )
            return ConsensusDecision(event=event, counted=False, duplicate_of=match.event, uncertain=False, reason=match.reason)
        if match and match.score >= 0.45:
            return ConsensusDecision(event=event, counted=True, duplicate_of=match.event, uncertain=True, reason=match.reason)
        return ConsensusDecision(event=event, counted=True, duplicate_of=None, uncertain=False, reason="no related camera event")

    def _drop_expired(self, now: float) -> None:
        max_age = max(self.config.uncertain_window_seconds, self.config.transition_window_seconds) * 2.0
        while self._recent and now - self._recent[0].timestamp > max_age:
            self._recent.popleft()

    def _best_match(self, event: CrossingEvent) -> _CandidateMatch | None:
        candidates: list[_CandidateMatch] = []
        for previous in self._recent:
            if previous.camera_id == event.camera_id:
                continue
            if previous.direction != event.direction:
                continue
            age = event.timestamp - previous.timestamp
            if age < 0 or age > self.config.uncertain_window_seconds:
                continue
            timing_score = self._timing_score(age)
            bbox_score = self._bbox_score(previous, event)
            zone_score = 1.0 if previous.zone == event.zone else 0.7
            score = (timing_score * 0.55) + (bbox_score * 0.30) + (zone_score * 0.15)
            candidates.append(_CandidateMatch(previous, score, f"time={age:.2f}s bbox_score={bbox_score:.2f}"))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.score)

    def _timing_score(self, age_seconds: float) -> float:
        expected = self.config.expected_travel_seconds
        transition = self.config.transition_window_seconds
        if age_seconds <= transition:
            distance = abs(age_seconds - expected)
            return max(0.0, 1.0 - (distance / max(transition, 0.001)))
        overflow = age_seconds - transition
        return max(0.0, 0.55 - (overflow / max(self.config.uncertain_window_seconds, 0.001)))

    def _bbox_score(self, first: CrossingEvent, second: CrossingEvent) -> float:
        largest = max(first.bbox.area, second.bbox.area, 1.0)
        ratio_delta = abs(first.bbox.area - second.bbox.area) / largest
        tolerance = max(self.config.bbox_area_ratio_tolerance, 0.001)
        return max(0.0, 1.0 - (ratio_delta / tolerance))
