from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, median
from time import monotonic
from typing import Any

import numpy as np


class Direction(str, Enum):
    IN = "in"
    OUT = "out"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


@dataclass(frozen=True)
class Detection:
    bbox: BoundingBox
    confidence: float
    class_id: int = 0
    label: str = "person"
    camera_id: str = ""
    timestamp: float = 0.0
    model_name: str = "YOLO26x person-only Detection HAILO10H"
    model_sha256: str = ""


class TrackState(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    OCCLUDED = "occluded"
    LOST = "lost"
    REIDENTIFIED = "reidentified"
    EXPIRED = "expired"


@dataclass(frozen=True)
class TrackedObject:
    track_id: int
    bbox: BoundingBox
    confidence: float
    camera_id: str
    age_frames: int = 0
    lost_frames: int = 0
    hits: int = 0
    state: TrackState = TrackState.TENTATIVE
    global_person_id: int | None = None
    embedding: tuple[float, ...] | None = None
    last_reid_at: float | None = None

    @property
    def confirmed(self) -> bool:
        return self.state in {TrackState.CONFIRMED, TrackState.REIDENTIFIED}


@dataclass(frozen=True)
class FramePacket:
    camera_id: str
    frame_id: int
    monotonic_time: float
    captured_at: float
    width: int
    height: int
    image: np.ndarray

    @classmethod
    def from_image(cls, camera_id: str, frame_id: int, image: np.ndarray, captured_at: float) -> "FramePacket":
        height, width = image.shape[:2]
        return cls(
            camera_id=camera_id,
            frame_id=frame_id,
            monotonic_time=monotonic(),
            captured_at=captured_at,
            width=width,
            height=height,
            image=image,
        )


@dataclass(frozen=True)
class CountingLine:
    start: tuple[float, float]
    end: tuple[float, float]
    in_positive_side: bool = True

    def side(self, point: tuple[float, float]) -> float:
        ax, ay = self.start
        bx, by = self.end
        px, py = point
        return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


@dataclass(frozen=True)
class CrossingEvent:
    camera_id: str
    local_track_id: int
    direction: Direction
    timestamp: float
    zone: str
    bbox: BoundingBox
    confidence: float
    global_person_id: int | None = None
    passage_id: str | None = None
    session_id: int | None = None
    embedding: tuple[float, ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsensusDecision:
    event: CrossingEvent
    counted: bool
    duplicate_of: CrossingEvent | None
    uncertain: bool
    reason: str


@dataclass
class CameraStats:
    connected: bool = False
    fps: float = 0.0
    dropped_frames: int = 0
    queue_replacements: int = 0
    last_error: str = ""


@dataclass(frozen=True)
class LatencySummary:
    count: int = 0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0


@dataclass
class LatencyWindow:
    max_samples: int = 300
    samples: dict[str, list[float]] = field(default_factory=dict)

    def add(self, values_ms: dict[str, float]) -> None:
        for name, value in values_ms.items():
            if value < 0:
                continue
            bucket = self.samples.setdefault(name, [])
            bucket.append(float(value))
            if len(bucket) > self.max_samples:
                del bucket[: len(bucket) - self.max_samples]

    def summaries(self) -> dict[str, LatencySummary]:
        return {name: summarize_latency(values) for name, values in self.samples.items()}


def summarize_latency(values: list[float]) -> LatencySummary:
    if not values:
        return LatencySummary()
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))
    p99_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.99))
    return LatencySummary(
        count=len(ordered),
        mean_ms=mean(ordered),
        median_ms=median(ordered),
        p95_ms=ordered[p95_index],
        p99_ms=ordered[p99_index],
        max_ms=ordered[-1],
    )


@dataclass
class RuntimeStats:
    inference_fps: float = 0.0
    inference_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    frame_age_ms: float = 0.0
    queue_length: int = 0
    queue_fill: float = 0.0
    dropped_frames: dict[str, int] = field(default_factory=dict)
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    temperature_c: float | None = None
    backend: str = ""
    hailo_status: str = "not checked"
    hailo_device: str = ""
    hailo_temperature_c: float | None = None
    hailo_inference_count: int = 0
    active_hef: str = ""
    active_hef_sha256: str = ""
    hailo_architecture: str = ""
    model_type: str = ""
    global_visible: int = 0
    timeouts: int = 0
    last_detection_at: float | None = None
    detector_active: bool = False
    detector_error: str = ""
    camera_obstructed: dict[str, bool] = field(default_factory=dict)
    reid_status: str = "not checked"
    reid_hef_sha256: str = ""
    reid_inference_count: int = 0
    reid_latency_ms: float = 0.0
    reid_cache_size: int = 0
    latency: dict[str, LatencySummary] = field(default_factory=dict)
