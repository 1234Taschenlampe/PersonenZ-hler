from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from math import cos, sin
from random import Random
from typing import Iterable

from .configuration import AppConfig
from .counter import GlobalCounts, LineCrossingCounter
from .dual_camera_consensus import DualCameraConsensus
from .identity_manager import GlobalIdentityManager
from .tracker import create_tracker
from .types import BoundingBox, CountingLine, Detection, Direction, TrackedObject


@dataclass(frozen=True)
class SyntheticPerson:
    person_id: int
    x: float
    y: float
    confidence: float = 0.95
    width: float = 120.0
    height: float = 220.0
    appearance_group: int | None = None

    @property
    def bbox(self) -> BoundingBox:
        return BoundingBox(
            self.x - self.width / 2.0,
            self.y - self.height / 2.0,
            self.x + self.width / 2.0,
            self.y + self.height / 2.0,
        )


@dataclass(frozen=True)
class SyntheticFrame:
    camera_id: str
    timestamp: float
    persons: tuple[SyntheticPerson, ...] = ()
    camera_online: bool = True
    router_online: bool = True
    detector_online: bool = True
    reid_online: bool = True


@dataclass
class EmulatorCounters:
    counts: GlobalCounts = field(default_factory=GlobalCounts)
    generated_frames: int = 0
    detector_failures: int = 0
    reid_failures: int = 0
    camera_dropouts: int = 0
    router_dropouts: int = 0
    identity_merges: int = 0
    uncertain: int = 0
    events: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    passed: bool
    expected: dict[str, int]
    actual: dict[str, int]
    diagnostics: tuple[str, ...] = ()


class DigitalTwin:
    """Hardware-free simulator for the production counting logic.

    The emulator replaces only physical cameras, YOLO/Hailo and OSNet inference.
    It still exercises the repository's tracker, global identity manager,
    A/neutral/B crossing logic and dual-camera consensus.
    """

    def __init__(self, config: AppConfig | None = None, seed: int = 1) -> None:
        self.config = config or self._default_config()
        self.random = Random(seed)
        self.trackers = {
            camera_id: create_tracker(self.config.tracking)[0]
            for camera_id in self.config.cameras
        }
        self.identity = GlobalIdentityManager(self.config.identity)
        self.consensus = DualCameraConsensus(self.config.consensus)
        self.counters = {
            camera_id: LineCrossingCounter(
                camera_id,
                CountingLine(camera.line_start, camera.line_end, camera.in_positive_side),
                self.config.tracking,
                camera,
            )
            for camera_id, camera in self.config.cameras.items()
        }
        self.stats = EmulatorCounters()
        self._frame_ids = {camera_id: 0 for camera_id in self.config.cameras}

    @staticmethod
    def _default_config() -> AppConfig:
        config = AppConfig()
        # The original synthetic fixtures explicitly traverse a mid-frame
        # line; physical deployments now default to confirmed edge exits.
        for camera in config.cameras.values():
            camera.counting_mode = "line"
        config.model.reid_required = True
        config.tracking.min_confirmed_hits = 2
        config.tracking.min_confirmed_track_hits = 3
        config.tracking.min_stable_zone_frames = 2
        config.tracking.iou_match_threshold = 0.15
        config.identity.reid_threshold = 0.62
        config.identity.match_window_seconds = 6.0
        config.identity.stale_seconds = 3.0
        config.identity.cache_ttl_seconds = 1800.0
        config.consensus.enabled = True
        return config

    def reset(self) -> None:
        self.__init__(self.config)

    def process(self, frame: SyntheticFrame) -> list[dict]:
        self.stats.generated_frames += 1
        camera_id = frame.camera_id
        self._frame_ids[camera_id] += 1

        if not frame.router_online:
            self.stats.router_dropouts += 1
            return []
        if not frame.camera_online:
            self.stats.camera_dropouts += 1
            return []
        if not frame.detector_online:
            self.stats.detector_failures += 1
            detections: list[Detection] = []
        else:
            detections = [
                Detection(
                    bbox=person.bbox,
                    confidence=person.confidence,
                    camera_id=camera_id,
                    timestamp=frame.timestamp,
                )
                for person in frame.persons
            ]

        tracks = self.trackers[camera_id].update(camera_id, detections)
        tracks = self._inject_embeddings(tracks, frame)
        before = len(self.identity.visible_global_ids)
        tracks = self.identity.update(camera_id, tracks, frame.timestamp, 1280, 720)
        after = len(self.identity.visible_global_ids)
        if len(frame.persons) > 1 and after < min(len(frame.persons), before + len(frame.persons)):
            self.stats.identity_merges += 1

        events = self.counters[camera_id].update(self._frame_ids[camera_id], tracks)
        emitted: list[dict] = []
        for event in events:
            decision = self.consensus.decide(event)
            self.stats.counts.apply(event.direction, decision.counted, decision.uncertain)
            if decision.uncertain:
                self.stats.uncertain += 1
            record = {
                "timestamp": frame.timestamp,
                "camera_id": camera_id,
                "direction": event.direction.value,
                "global_person_id": event.global_person_id,
                "counted": decision.counted,
                "uncertain": decision.uncertain,
                "reason": decision.reason,
            }
            self.stats.events.append(record)
            emitted.append(record)
        return emitted

    def _inject_embeddings(self, tracks: list[TrackedObject], frame: SyntheticFrame) -> list[TrackedObject]:
        if not frame.reid_online:
            self.stats.reid_failures += len([track for track in tracks if track.lost_frames == 0])
            return tracks
        output: list[TrackedObject] = []
        for track in tracks:
            if track.lost_frames != 0:
                output.append(track)
                continue
            person = self._nearest_person(track.bbox, frame.persons)
            if person is None:
                output.append(track)
                continue
            group = person.person_id if person.appearance_group is None else person.appearance_group
            output.append(replace(track, embedding=self._embedding(group)))
        return output

    @staticmethod
    def _nearest_person(bbox: BoundingBox, persons: Iterable[SyntheticPerson]) -> SyntheticPerson | None:
        cx, cy = bbox.center
        best: tuple[float, SyntheticPerson] | None = None
        for person in persons:
            px, py = person.bbox.center
            distance = (cx - px) ** 2 + (cy - py) ** 2
            if best is None or distance < best[0]:
                best = (distance, person)
        return None if best is None else best[1]

    @staticmethod
    def _embedding(group: int, dimensions: int = 64) -> tuple[float, ...]:
        # Deterministic unit vector: same appearance_group => near-identical ReID.
        values = [sin((group + 1) * (index + 1) * 0.173) + cos((group + 3) * (index + 1) * 0.071) for index in range(dimensions)]
        norm = sum(value * value for value in values) ** 0.5
        return tuple(value / norm for value in values)

    @property
    def snapshot(self) -> dict[str, int]:
        return {
            "inside": self.stats.counts.inside,
            "entered": self.stats.counts.entered,
            "exited": self.stats.counts.exited,
            "suppressed": self.stats.counts.suppressed_duplicates,
            "uncertain": self.stats.counts.uncertain_consensus,
        }


def _crossing_frames(
    camera_id: str,
    person_id: int,
    start: float,
    direction: Direction,
    *,
    x: float = 420.0,
    appearance_group: int | None = None,
    online: bool = True,
) -> list[SyntheticFrame]:
    if direction is Direction.IN:
        ys = [245, 255, 270, 310, 350, 370, 405, 430, 445]
    else:
        ys = [445, 430, 405, 370, 350, 310, 270, 255, 245]
    return [
        SyntheticFrame(
            camera_id=camera_id,
            timestamp=start + index * 0.1,
            persons=(SyntheticPerson(person_id, x, y, appearance_group=appearance_group),),
            camera_online=online,
        )
        for index, y in enumerate(ys)
    ]


def _run_frames(twin: DigitalTwin, frames: Iterable[SyntheticFrame]) -> None:
    for frame in frames:
        twin.process(frame)


def scenario_normal_entry() -> ScenarioResult:
    twin = DigitalTwin()
    _run_frames(twin, _crossing_frames("camera_1", 1, 10.0, Direction.IN))
    return _result("normal_entry", twin, {"entered": 1, "exited": 0, "inside": 1})


def scenario_normal_exit() -> ScenarioResult:
    twin = DigitalTwin()
    _run_frames(twin, _crossing_frames("camera_2", 1, 10.0, Direction.OUT))
    return _result("normal_exit", twin, {"entered": 0, "exited": 1, "inside": 0})


def scenario_turnaround() -> ScenarioResult:
    twin = DigitalTwin()
    ys = [245, 255, 300, 345, 365, 345, 300, 255, 245]
    frames = [SyntheticFrame("camera_1", 10.0 + i * 0.1, (SyntheticPerson(1, 420, y),)) for i, y in enumerate(ys)]
    _run_frames(twin, frames)
    return _result("turnaround", twin, {"entered": 0, "exited": 0, "inside": 0})


def scenario_two_people() -> ScenarioResult:
    twin = DigitalTwin()
    first = _crossing_frames("camera_1", 1, 10.0, Direction.IN, x=340)
    second = _crossing_frames("camera_1", 2, 10.0, Direction.IN, x=760)
    frames = [
        SyntheticFrame("camera_1", first[i].timestamp, (first[i].persons[0], second[i].persons[0]))
        for i in range(len(first))
    ]
    _run_frames(twin, frames)
    return _result("two_people", twin, {"entered": 2, "exited": 0, "inside": 2})


def scenario_short_camera_dropout() -> ScenarioResult:
    twin = DigitalTwin()
    frames = _crossing_frames("camera_1", 1, 10.0, Direction.IN)
    damaged = [replace(frame, camera_online=False) if index in {3, 4} else frame for index, frame in enumerate(frames)]
    _run_frames(twin, damaged)
    result = _result("short_camera_dropout", twin, {"entered": 1, "exited": 0, "inside": 1})
    return replace(result, diagnostics=result.diagnostics + (f"camera_dropouts={twin.stats.camera_dropouts}",))


def scenario_router_outage_no_false_count() -> ScenarioResult:
    twin = DigitalTwin()
    frames = _crossing_frames("camera_1", 1, 10.0, Direction.IN)
    _run_frames(twin, [replace(frame, router_online=False) for frame in frames])
    result = _result("router_outage_no_false_count", twin, {"entered": 0, "exited": 0, "inside": 0})
    return replace(result, diagnostics=result.diagnostics + (f"router_dropouts={twin.stats.router_dropouts}",))


def scenario_detector_outage_no_false_count() -> ScenarioResult:
    twin = DigitalTwin()
    frames = _crossing_frames("camera_1", 1, 10.0, Direction.IN)
    _run_frames(twin, [replace(frame, detector_online=False) for frame in frames])
    result = _result("detector_outage_no_false_count", twin, {"entered": 0, "exited": 0, "inside": 0})
    return replace(result, diagnostics=result.diagnostics + (f"detector_failures={twin.stats.detector_failures}",))


def scenario_same_person_cross_camera_reid() -> ScenarioResult:
    twin = DigitalTwin()
    # Identity-only test: same synthetic appearance on both cameras within match window.
    f1 = SyntheticFrame("camera_1", 10.0, (SyntheticPerson(77, 420, 300, appearance_group=77),))
    f2 = SyntheticFrame("camera_2", 10.5, (SyntheticPerson(77, 430, 310, appearance_group=77),))
    for _ in range(3):
        twin.process(f1)
    twin.process(f2)
    ids = twin.identity.visible_global_ids
    passed = len(ids) == 1
    return ScenarioResult(
        "same_person_cross_camera_reid",
        passed,
        {"global_visible": 1},
        {"global_visible": len(ids)},
        ("same appearance embedding on both cameras",),
    )


def scenario_similar_people_simultaneously() -> ScenarioResult:
    twin = DigitalTwin()
    # Different persons deliberately share the same appearance embedding. The
    # emulator expects topology/time logic to keep them separate when simultaneous.
    for _ in range(3):
        twin.process(SyntheticFrame("camera_1", 10.0, (SyntheticPerson(1, 300, 300, appearance_group=999),)))
    twin.process(SyntheticFrame("camera_2", 10.0, (SyntheticPerson(2, 900, 300, appearance_group=999),)))
    visible = len(twin.identity.visible_global_ids)
    return ScenarioResult(
        "similar_people_simultaneously",
        visible == 2,
        {"global_visible": 2},
        {"global_visible": visible},
        ("two distinct people intentionally have identical ReID embeddings",),
    )


def scenario_reid_unavailable() -> ScenarioResult:
    twin = DigitalTwin()
    f1 = SyntheticFrame("camera_1", 10.0, (SyntheticPerson(1, 420, 300),), reid_online=False)
    f2 = SyntheticFrame("camera_2", 10.5, (SyntheticPerson(1, 430, 310),), reid_online=False)
    for _ in range(3):
        twin.process(f1)
    twin.process(f2)
    visible = len(twin.identity.visible_global_ids)
    # Safe behavior: without ReID, don't merge identities merely from geometry.
    return ScenarioResult(
        "reid_unavailable",
        visible == 2,
        {"global_visible": 2},
        {"global_visible": visible},
        (f"reid_failures={twin.stats.reid_failures}",),
    )


def scenario_long_gap_reid() -> ScenarioResult:
    twin = DigitalTwin()
    for _ in range(3):
        twin.process(SyntheticFrame("camera_1", 10.0, (SyntheticPerson(42, 420, 300),)))
    twin.process(SyntheticFrame("camera_2", 40.0, (SyntheticPerson(42, 430, 310),)))
    visible = len(twin.identity.visible_global_ids)
    # Current target requirement is a 30-minute ReID cache. This scenario is
    # intentionally strict: it exposes if match_window_seconds defeats the cache.
    return ScenarioResult(
        "long_gap_reid_30s",
        visible == 1,
        {"global_visible": 1},
        {"global_visible": visible},
        ("same person returns on other camera after 30 seconds",),
    )


def _result(name: str, twin: DigitalTwin, expected: dict[str, int]) -> ScenarioResult:
    actual = twin.snapshot
    subset = {key: actual[key] for key in expected}
    diagnostics: list[str] = []
    if subset != expected:
        diagnostics.append(f"events={json.dumps(twin.stats.events, sort_keys=True)}")
    return ScenarioResult(name, subset == expected, expected, subset, tuple(diagnostics))


SCENARIOS = {
    "normal_entry": scenario_normal_entry,
    "normal_exit": scenario_normal_exit,
    "turnaround": scenario_turnaround,
    "two_people": scenario_two_people,
    "short_camera_dropout": scenario_short_camera_dropout,
    "router_outage_no_false_count": scenario_router_outage_no_false_count,
    "detector_outage_no_false_count": scenario_detector_outage_no_false_count,
    "same_person_cross_camera_reid": scenario_same_person_cross_camera_reid,
    "similar_people_simultaneously": scenario_similar_people_simultaneously,
    "reid_unavailable": scenario_reid_unavailable,
    "long_gap_reid_30s": scenario_long_gap_reid,
}


def run_scenarios(names: Iterable[str]) -> list[ScenarioResult]:
    return [SCENARIOS[name]() for name in names]


def _print_results(results: list[ScenarioResult]) -> None:
    width = max(len(result.name) for result in results)
    for result in results:
        state = "PASS" if result.passed else "FAIL"
        print(f"{state:4}  {result.name:<{width}} expected={result.expected} actual={result.actual}")
        for diagnostic in result.diagnostics:
            print(f"      {diagnostic}")
    passed = sum(result.passed for result in results)
    print(f"\n{passed}/{len(results)} scenarios passed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hardware-free visitor counter digital twin")
    parser.add_argument("--scenario", action="append", choices=sorted(SCENARIOS), help="Run one scenario; repeatable")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    args = parser.parse_args()
    if args.list:
        for name in sorted(SCENARIOS):
            print(name)
        return 0
    names = args.scenario or list(SCENARIOS)
    results = run_scenarios(names)
    _print_results(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
