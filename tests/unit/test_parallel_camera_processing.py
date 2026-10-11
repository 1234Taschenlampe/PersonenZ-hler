"""Parallel camera dispatch and safe shared-Hailo fallback, without hardware."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
from time import sleep, time
from types import SimpleNamespace

import numpy as np

from visitor_counter.configuration import AppConfig
from visitor_counter.inference_pipeline import ProcessingPipeline
from visitor_counter.types import FramePacket, RuntimeStats


def _packet(camera_id: str) -> FramePacket:
    return FramePacket.from_image(
        camera_id, 1, np.zeros((100, 100, 3), dtype=np.uint8), time()
    )


def test_dispatches_two_cameras_simultaneously_without_reordering_tracks(tmp_path):
    config = AppConfig()
    config.model.detector_enabled = False
    config.model.reid_required = False
    config.database.encryption_required = False
    config.database.store_events = False
    config.database.path = str(tmp_path / "parallel.sqlite3")
    stopped = Event()
    remaining = deque((_packet("camera_1"), _packet("camera_2")))
    dispatch_lock = Lock()

    class Hub:
        maxsize = 2

        def get_next(self, camera_order, *_args, **_kwargs):
            with dispatch_lock:
                for index, packet in enumerate(remaining):
                    if packet.camera_id in camera_order:
                        del remaining[index]
                        return packet
            return None

        def qsize(self):
            return len(remaining)

        def dropped_counts(self):
            return {}

    pipeline = ProcessingPipeline(config, tmp_path, Hub(), stopped)
    both_running = Barrier(2, timeout=4.0)
    observations = []
    observed_lock = Lock()

    def process(packet):
        with observed_lock:
            observations.append(packet.camera_id)
        both_running.wait()
        stopped.set()

    pipeline._process_packet = process
    pipeline.run()
    assert set(observations) == {"camera_1", "camera_2"}


def test_two_dedicated_hailo_contexts_run_at_the_same_time():
    ready_together = Barrier(2, timeout=4.0)

    class FakeHailo:
        ready = True
        last_stage_ms = {}
        last_latency_ms = 3.0
        inference_count = 0

        def infer(self, _image):
            ready_together.wait()
            self.inference_count += 1
            return []

    pipeline = object.__new__(ProcessingPipeline)
    pipeline.config = AppConfig()
    pipeline.hailo = first = FakeHailo()
    second = FakeHailo()
    pipeline._hailo_workers = {"camera_1": first, "camera_2": second}
    pipeline._shared_hailo_lock = Lock()
    pipeline._camera_hailo_stage_ms = {}
    pipeline._camera_hailo_latency_ms = {}
    pipeline.runtime_stats = RuntimeStats()
    pipeline._camera_ai_ticks = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        completed = list(pool.map(pipeline._detect, (_packet("camera_1"), _packet("camera_2"))))
    assert completed == [[], []]
    assert first.inference_count == second.inference_count == 1


def test_shared_hailo_context_is_serialized_when_second_context_unavailable():
    class FakeHailo:
        ready = True
        last_stage_ms = {}
        last_latency_ms = 3.0
        inference_count = 0

        def __init__(self):
            self.in_progress = 0
            self.max_overlap = 0
            self.lock = Lock()

        def infer(self, _image):
            with self.lock:
                self.in_progress += 1
                self.max_overlap = max(self.max_overlap, self.in_progress)
            sleep(0.02)
            with self.lock:
                self.in_progress -= 1
                self.inference_count += 1
            return []

    pipeline = object.__new__(ProcessingPipeline)
    pipeline.config = AppConfig()
    pipeline.hailo = shared = FakeHailo()
    pipeline._hailo_workers = {"camera_1": shared, "camera_2": shared}
    pipeline._shared_hailo_lock = Lock()
    pipeline._camera_hailo_stage_ms = {}
    pipeline._camera_hailo_latency_ms = {}
    pipeline.runtime_stats = RuntimeStats()
    pipeline._camera_ai_ticks = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(pipeline._detect, (_packet("camera_1"), _packet("camera_2"))))
    assert shared.max_overlap == 1
    assert shared.inference_count == 2


def test_second_hailo_allocation_failure_retains_first_model(monkeypatch, tmp_path):
    class FailedSecondContext:
        def __init__(self, *_args):
            self.closed = False

        def initialize(self):
            raise RuntimeError("second context unavailable")

        def close(self):
            self.closed = True

    import visitor_counter.inference_pipeline as module
    monkeypatch.setattr(module, "HailoManager", FailedSecondContext)
    pipeline = object.__new__(ProcessingPipeline)
    pipeline.config = AppConfig()
    pipeline.config.model.reid_required = False
    pipeline.project_root = tmp_path
    pipeline.model = SimpleNamespace(hef_path=Path("model.hef"))
    pipeline._camera_order = ["camera_1", "camera_2"]
    primary = SimpleNamespace(inference_count=4)
    pipeline._hailo_workers = {"camera_1": primary, "camera_2": primary}
    pipeline._reid_workers = {}
    pipeline.runtime_stats = RuntimeStats()
    pipeline._initialize_parallel_engines()
    assert pipeline._hailo_workers["camera_2"] is primary
    assert pipeline.runtime_stats.parallel_inference_mode == (
        "parallel_camera_workers_serialized_shared_models"
    )

def test_secondary_hailo_runtime_error_falls_back_to_primary_context():
    from visitor_counter.hailo_manager import HailoUnavailableError

    class Primary:
        ready = True
        last_stage_ms = {}
        last_latency_ms = 2.0
        inference_count = 0

        def infer(self, _image):
            self.inference_count += 1
            return []

    class Secondary:
        last_stage_ms = {}
        last_latency_ms = 3.0
        inference_count = 0
        closed = False

        def infer(self, _image):
            raise HailoUnavailableError("secondary Hailo context lost")

        def close(self):
            self.closed = True

    pipeline = object.__new__(ProcessingPipeline)
    pipeline.config = AppConfig()
    pipeline.hailo = primary = Primary()
    secondary = Secondary()
    pipeline._hailo_workers = {"camera_1": primary, "camera_2": secondary}
    pipeline._shared_hailo_lock = Lock()
    pipeline._camera_hailo_stage_ms = {}
    pipeline._camera_hailo_latency_ms = {}
    pipeline.runtime_stats = RuntimeStats()
    pipeline._camera_ai_ticks = {}
    assert pipeline._detect(_packet("camera_2")) == []
    assert secondary.closed
    assert pipeline._hailo_workers["camera_2"] is primary
    assert primary.inference_count == 1
    assert pipeline.runtime_stats.parallel_inference_mode == (
        "parallel_camera_workers_serialized_shared_models"
    )

def test_two_camera_tracks_both_reach_production_counts(tmp_path):
    from visitor_counter.enhanced_counting import EnhancedProcessingPipeline
    from visitor_counter.types import BoundingBox, Detection

    config = AppConfig()
    config.model.detector_enabled = False
    config.model.reid_required = False
    config.database.encryption_required = False
    config.database.store_events = False
    config.database.path = str(tmp_path / "two-cameras.sqlite")
    config.tracking.min_confirmed_hits = 3
    config.tracking.min_confirmed_track_hits = 2
    config.tracking.min_stable_zone_frames = 1
    config.tracking.zone_hysteresis_pixels = 0
    for camera in config.cameras.values():
        camera.width = camera.height = 200
        camera.line_start, camera.line_end = (0, 100), (200, 100)
        camera.counting_mode = "line"
        camera.entry_direction, camera.exit_direction = "A_to_B", "B_to_A"

    stopped = Event()
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    remaining = deque(
        FramePacket.from_image(camera_id, i, frame.copy(), time())
        for i in range(1, 4)
        for camera_id in ("camera_1", "camera_2")
    )
    dispatch_lock = Lock()

    class Hub:
        maxsize = 2

        def get_next(self, camera_order, *_args, **_kwargs):
            with dispatch_lock:
                for index, packet in enumerate(remaining):
                    if packet.camera_id in camera_order:
                        del remaining[index]
                        return packet
                if not remaining:
                    stopped.set()
            return None

        def qsize(self):
            return len(remaining)

        def dropped_counts(self):
            return {}

    pipeline = EnhancedProcessingPipeline(config, tmp_path, Hub(), stopped)
    for camera_id in config.cameras:
        pipeline.obstruction_detectors[camera_id] = SimpleNamespace(
            update=lambda _image: SimpleNamespace(obstructed=False, reason="clear")
        )
    pipeline._detect = lambda packet: [
        Detection(
            BoundingBox(75, 30 if packet.frame_id == 1 else 70,
                        115, 130 if packet.frame_id == 1 else 170), 0.9
        )
    ]
    pipeline.run()
    assert pipeline.runtime_stats.camera_processed_frames == {
        "camera_1": 3, "camera_2": 3
    }
    assert pipeline.counters["camera_1"].counts.entered == 1
    assert pipeline.counters["camera_2"].counts.entered == 1
    assert pipeline.global_counts.entered == 2
    assert pipeline.global_counts.inside == 2
