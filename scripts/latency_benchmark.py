from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from threading import Event
from time import monotonic

import psutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from visitor_counter.camera_manager import CameraCapture, LatestFrameHub  # noqa: E402
from visitor_counter.configuration import CameraConfig, ModelConfig, load_config  # noqa: E402
from visitor_counter.hailo_manager import HailoManager  # noqa: E402
from visitor_counter.tracker import create_tracker  # noqa: E402
from visitor_counter.types import LatencyWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure end-to-end camera to Hailo latency without the GUI.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--hef", type=Path, default=Path("models/yolo11x_hailo10h.hef"))
    parser.add_argument("--model-name", default="YOLO11x Detection HAILO10H")
    parser.add_argument("--cameras", type=int, choices=(1, 2), default=2)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--tracker", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", type=Path, default=Path("logs/latency_benchmark.json"))
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    config = load_config(project_root / "config" / "config.yaml")
    camera_items = list(config.cameras.items())[: args.cameras]
    camera_configs: list[CameraConfig] = []
    for camera_id, camera_config in camera_items:
        camera_config.fps = args.fps
        camera_configs.append(camera_config)

    model_config = ModelConfig(
        hef_path=str(args.hef),
        model_name=args.model_name,
        custom_target_hef_path=str(args.hef),
        target_hef_path=str(args.hef),
        require_custom_yolo26x=False,
        detector_fallback_enabled=False,
        allow_fallback=False,
        output_format="hailo_nms",
        input_size=config.model.input_size,
        confidence_threshold=config.model.confidence_threshold,
        iou_threshold=config.model.iou_threshold,
        reid_required=False,
    )
    hef_path = args.hef if args.hef.is_absolute() else project_root / args.hef
    hailo = HailoManager(model_config, hef_path)
    hub = LatestFrameHub([camera.camera_id for camera in camera_configs])
    stop_event = Event()
    captures = [CameraCapture(camera, hub, stop_event) for camera in camera_configs]
    trackers = {camera.camera_id: create_tracker(config.tracking)[0] for camera in camera_configs}
    latency = LatencyWindow(max_samples=2000)
    cpu_samples: list[float] = []
    ram_samples: list[float] = []
    processed_by_camera = {camera.camera_id: 0 for camera in camera_configs}
    detections_by_camera = {camera.camera_id: 0 for camera in camera_configs}
    last_camera_id: str | None = None

    hailo.initialize()
    started = monotonic()
    try:
        for capture in captures:
            capture.start()
        while monotonic() - started < args.duration:
            packet = hub.get_next(list(processed_by_camera), last_camera_id, timeout=0.2, max_age_seconds=0.5)
            if packet is None:
                cpu_samples.append(psutil.cpu_percent(interval=None))
                ram_samples.append(psutil.virtual_memory().percent)
                continue
            last_camera_id = packet.camera_id
            frame_started = monotonic()
            detections = hailo.infer(packet.image)
            tracker_start = monotonic()
            tracks = trackers[packet.camera_id].update(packet.camera_id, detections) if args.tracker else []
            tracker_ms = (monotonic() - tracker_start) * 1000.0
            now = monotonic()
            processed_by_camera[packet.camera_id] += 1
            detections_by_camera[packet.camera_id] += len(detections)
            stage = {
                "frame_age_at_dequeue_ms": (frame_started - packet.monotonic_time) * 1000.0,
                "tracker_ms": tracker_ms,
                "osnet_reid_ms": 0.0,
                "gui_transfer_ms": 0.0,
                "draw_boxes_ms": 0.0,
                "end_to_end_ms": (now - packet.monotonic_time) * 1000.0,
                "processing_total_ms": (now - frame_started) * 1000.0,
                "tracked_objects": float(len(tracks)),
            }
            stage.update(hailo.last_stage_ms)
            latency.add(stage)
            cpu_samples.append(psutil.cpu_percent(interval=None))
            ram_samples.append(psutil.virtual_memory().percent)
    finally:
        stop_event.set()
        for capture in captures:
            capture.join(timeout=2.0)
        hailo.close()

    elapsed = monotonic() - started
    hef_sha256 = hailo.hef_sha256
    backend = hailo.backend
    hailo_device = hailo.hailo_device
    hailo_architecture = hailo.hailo_architecture
    hailo_inference_count = hailo.inference_count
    report = {
        "duration_seconds": elapsed,
        "hef": str(hef_path),
        "hef_sha256": hef_sha256,
        "model_name": args.model_name,
        "backend": backend,
        "hailo_device": hailo_device,
        "hailo_architecture": hailo_architecture,
        "hailo_inference_count": hailo_inference_count,
        "input_fps": args.fps,
        "camera_count": args.cameras,
        "tracker_enabled": args.tracker,
        "osnet_enabled": False,
        "gui_enabled": False,
        "processed_by_camera": processed_by_camera,
        "detections_by_camera": detections_by_camera,
        "capture_fps": {capture.config.camera_id: capture.stats.fps for capture in captures},
        "dropped_frames": hub.dropped_counts(),
        "queue_length": hub.qsize(),
        "cpu_percent_mean": mean(cpu_samples) if cpu_samples else None,
        "ram_percent_mean": mean(ram_samples) if ram_samples else None,
        "latency": {name: asdict(summary) for name, summary in latency.summaries().items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    del hailo
    gc.collect()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
