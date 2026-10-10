from collections import deque
from threading import Event
from types import SimpleNamespace
from time import time

import numpy as np

from visitor_counter.configuration import AppConfig
from visitor_counter.enhanced_counting import EnhancedProcessingPipeline
from visitor_counter.inference_pipeline import ProcessingPipeline
from visitor_counter.types import BoundingBox, Detection, FramePacket, RuntimeStats


def test_one_camera_crossing_before_confirmation_reaches_counter(tmp_path):
    config = AppConfig()
    config.model.detector_enabled = False  # fake detector, no hardware required
    config.model.reid_required = False
    config.database.encryption_required = False
    config.database.store_events = False
    config.database.path = str(tmp_path / "events.sqlite")
    config.tracking.min_confirmed_hits = 3
    config.tracking.min_confirmed_track_hits = 2
    config.tracking.min_stable_zone_frames = 1
    config.tracking.zone_hysteresis_pixels = 0
    camera = config.cameras["camera_1"]
    camera.width = camera.height = 200
    camera.line_start, camera.line_end = (0, 100), (200, 100)
    camera.counting_mode = "line"
    camera.entry_direction, camera.exit_direction = "A_to_B", "B_to_A"
    stopped = Event()
    packets = deque(FramePacket.from_image("camera_1", i, np.zeros((200, 200, 3), dtype=np.uint8), time()) for i in range(1, 4))

    class Queue:
        maxsize = 2

        def get_next(self, *args, **kwargs):
            if packets:
                return packets.popleft()
            stopped.set()
            return None

        def qsize(self):
            return 0

        def dropped_counts(self):
            return {}

    pipeline = EnhancedProcessingPipeline(config, tmp_path, Queue(), stopped)
    pipeline.obstruction_detectors["camera_1"] = SimpleNamespace(update=lambda image: SimpleNamespace(obstructed=False, reason="clear"))
    pipeline._detect = lambda packet: [Detection(BoundingBox(75, 30 if packet.frame_id == 1 else 70, 115, 130 if packet.frame_id == 1 else 170), 0.9)]
    pipeline.run()
    assert pipeline.runtime_stats.camera_processed_frames == {"camera_1": 3}
    assert pipeline.counters["camera_1"].counts.entered == 1
    assert pipeline.counters["camera_2"].counts.entered == 0
    assert pipeline.global_counts.entered == 1
    assert pipeline.global_counts.inside == 1


def test_camera_ai_fps_drops_to_zero_when_no_more_frames_arrive(monkeypatch):
    pipeline = object.__new__(ProcessingPipeline)
    pipeline.runtime_stats = RuntimeStats()
    pipeline._camera_ai_ticks = {"camera_1": deque([9.5, 9.8])}
    pipeline.stats_callback = None
    monkeypatch.setattr("visitor_counter.inference_pipeline.monotonic", lambda: 10.0)
    pipeline._emit_stats()
    assert pipeline.runtime_stats.camera_ai_fps == {"camera_1": 2.0}
    monkeypatch.setattr("visitor_counter.inference_pipeline.monotonic", lambda: 11.0)
    pipeline._emit_stats()
    assert pipeline.runtime_stats.camera_ai_fps == {"camera_1": 0.0}
