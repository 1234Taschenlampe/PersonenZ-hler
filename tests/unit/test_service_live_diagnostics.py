import json
from types import SimpleNamespace
from visitor_counter.service import VisitorCounterService
from visitor_counter.configuration import CameraConfig
from visitor_counter.counter import GlobalCounts
from visitor_counter.types import CameraStats, RuntimeStats


def test_service_reports_received_and_processed_frames_and_rejections(tmp_path, monkeypatch):
    service = object.__new__(VisitorCounterService)
    service._last_status_write_at = 0
    service.live_status_path = tmp_path / "live.json"
    service.config = SimpleNamespace(model=SimpleNamespace(detector_enabled=True, reid_required=True))
    service.captures = [SimpleNamespace(config=CameraConfig(camera_id="camera_1"),
                                       stats=CameraStats(frame_width=2560, frame_height=1920),
                                       _frame_id=37)]
    counter = SimpleNamespace(counts=SimpleNamespace(visible=1, entered=0, exited=0),
                              rejected_events=2, last_rejection_reason="track not confirmed",
                              rejection_counts={"track not confirmed": 2})
    service.pipeline = SimpleNamespace(counters={"camera_1": counter})
    stats = RuntimeStats(camera_processed_frames={"camera_1": 10},
                         camera_ai_processed_frames={"camera_1": 9},
                         camera_ai_fps={"camera_1": 6.0},
                         camera_detection_confidence={"camera_1": 0.91},
                         camera_inference_status={"camera_1": "active"},
                         camera_consensus_rejections={"camera_1": 3},
                         camera_last_consensus_reason={"camera_1": "duplicate identity"},
                         camera_person_detections={"camera_1": 1},
                         camera_confirmed_tracks={"camera_1": 1},
                         camera_inference_latency_ms={"camera_1": 14.5},
                         hailo_status="active", reid_status="active")
    monkeypatch.setattr("visitor_counter.service.read_host_metrics", lambda: {"temperature_c": 52.0})
    service._on_stats(stats, GlobalCounts())
    payload = json.loads(service.live_status_path.read_text())
    camera = payload["cameras"][0]
    assert (camera["actual_width"], camera["actual_height"]) == (2560, 1920)
    assert camera["frames_received"] == 37
    assert camera["frames_processed"] == 10
    assert camera["ai_processed_frames"] == 9
    assert camera["ai_fps"] == 6.0
    assert camera["detection_confidence"] == 0.91
    assert camera["inference_status"] == "active"
    assert camera["consensus_rejected_events"] == 3
    assert camera["last_consensus_rejection_reason"] == "duplicate identity"
    assert camera["inference_latency_ms"] == 14.5
    assert camera["last_rejection_reason"] == "track not confirmed"
    assert payload["counts"]["entered"] == 0
    assert payload["runtime"]["temperature_c"] == 52.0


def test_service_one_configured_camera_starts_and_pipeline_failure_returns_error(monkeypatch):
    from threading import Event
    from pathlib import Path

    class Capture:
        def __init__(self, device):
            self.config = CameraConfig(camera_id=str(device), device=device)
            self.started = False
            self.joined = False

        def start(self):
            self.started = True

        def join(self, timeout):
            assert self.started
            self.joined = True

    captures = [Capture("rtsp://example.invalid/Preview_01_main"), Capture(None)]
    service = object.__new__(VisitorCounterService)
    service.project_root = Path(".")
    service.paths = SimpleNamespace(license_file=Path("license"), license_public_key=Path("key"))
    service.config = SimpleNamespace(cameras={str(i): c.config for i, c in enumerate(captures)})
    service.captures = captures
    service.stop_event = Event()
    service.pipeline = SimpleNamespace(start=lambda: None, is_alive=lambda: False, join=lambda timeout: None)
    service.preview = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr("visitor_counter.service.enforce_license", lambda *args, **kwargs: SimpleNamespace(license_id="", online_checked=False))
    monkeypatch.setattr("visitor_counter.service.privacy_readiness_errors", lambda config: [])
    assert service.run() == 1
    assert captures[0].started and captures[0].joined
    assert not captures[1].started and not captures[1].joined
