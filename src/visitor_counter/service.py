from __future__ import annotations

import json
import logging
import signal
from pathlib import Path
from threading import Event
from time import monotonic, sleep, time
from urllib.parse import urlsplit

from .camera_manager import CameraCapture, LatestFrameHub, camera_source_kind
from .configuration import load_config, privacy_readiness_errors
from .counter import GlobalCounts
from .diagnostics import redact_sensitive, read_host_metrics
from .enhanced_counting import EnhancedProcessingPipeline
from .license_guard import LicenseError, enforce_license
from .logging_setup import configure_logging
from .runtime_paths import RuntimePaths
from .types import RuntimeStats
from .video_stream import LocalPreviewExporter

LOGGER = logging.getLogger(__name__)


class VisitorCounterService:
    """Headless production runtime for two-camera operation.

    This is intentionally independent of the PySide GUI. It lets the Raspberry
    Pi run two WLAN/IP cameras continuously while the local GUI, Android app and
    two display clients consume status through the existing API.
    """

    def __init__(self, project_root: Path | RuntimePaths) -> None:
        self.paths = (
            project_root
            if isinstance(project_root, RuntimePaths)
            else RuntimePaths.discover(project_root)
        )
        self.project_root = self.paths.project_root
        self.config = load_config(self.paths.config_file)
        self.stop_event = Event()
        self.frame_hub = LatestFrameHub(list(self.config.cameras))
        self.captures = [
            CameraCapture(camera, self.frame_hub, self.stop_event)
            for camera in self.config.cameras.values()
        ]
        self.live_status_path = self.paths.live_status_file
        self._last_status_write_at = 0.0
        self.preview = LocalPreviewExporter(
            self.project_root, enabled=self.config.display.show_camera_preview,
            anonymization_mode=self.config.display.anonymization_mode,
            pixel_size=self.config.display.pixel_size,
        )
        self.pipeline = EnhancedProcessingPipeline(
            self.config,
            self.project_root,
            self.frame_hub,
            self.stop_event,
            stats_callback=self._on_stats,
            frame_callback=self.preview.submit if self.preview.enabled else None,
        )
        self.pipeline._gui_interval_seconds = 1.0 / max(self.preview.target_fps, 1.0)

    def run(self) -> int:
        try:
            license_decision = enforce_license(
                self.project_root,
                license_path=self.paths.license_file,
                public_key_path=self.paths.license_public_key,
            )
        except LicenseError as exc:
            LOGGER.error("STARTUP_BLOCKED license: %s", exc)
            return 4
        LOGGER.info(
            "LICENSE_OK id=%s online=%s",
            license_decision.license_id or "not-enforced",
            license_decision.online_checked,
        )

        errors = privacy_readiness_errors(self.config)
        if errors:
            for error in errors:
                LOGGER.error("STARTUP_BLOCKED %s", error)
            return 2

        missing = [
            camera.camera_id
            for camera in self.config.cameras.values()
            if not camera.device
        ]
        if len(missing) == len(self.config.cameras):
            LOGGER.error("STARTUP_BLOCKED no camera sources configured")
            return 3
        if missing:
            LOGGER.warning(
                "CAMERA_SLOTS_UNCONFIGURED %s; other cameras will continue",
                ", ".join(missing),
            )

        active_captures = [capture for capture in self.captures if capture.config.device]
        for capture in active_captures:
            capture.start()
        self.pipeline.start()

        exit_code = 0
        while not self.stop_event.is_set():
            if not self.pipeline.is_alive():
                exit_code = 1
                LOGGER.error("Inference pipeline stopped unexpectedly")
                self.stop_event.set()
                break
            sleep(0.5)

        for capture in active_captures:
            capture.join(timeout=3.0)
        self.pipeline.join(timeout=5.0)
        self.preview.close()
        return exit_code

    def stop(self) -> None:
        self.stop_event.set()

    def _on_stats(self, stats: RuntimeStats, counts: GlobalCounts) -> None:
        # Avoid rewriting the live-status file on every captured frame.
        tick = monotonic()
        if tick - self._last_status_write_at < 1.0:
            return
        self._last_status_write_at = tick
        now = time()
        cameras = []
        for capture in self.captures:
            camera = capture.config
            cs = capture.stats
            camera_path = urlsplit(camera.device or "").path.lower()
            profile = "main" if camera_path.endswith("_main") else (
                "sub" if camera_path.endswith("_sub") else "unknown"
            )
            cameras.append(
                {
                    "camera_id": camera.camera_id,
                    "name": camera.display_name,
                    "role": camera.role,
                    "source": camera_source_kind(camera.device),
                    "wanted_fps": camera.fps,
                    "width": cs.frame_width or camera.width,
                    "height": cs.frame_height or camera.height,
                    "actual_width": cs.frame_width,
                    "actual_height": cs.frame_height,
                    "configured_width": camera.width,
                    "configured_height": camera.height,
                    "stream_profile": profile,
                    "status": cs.state,
                    "actual_fps": round(cs.fps, 1),
                    "last_frame_time": cs.last_frame_time,
                    "seconds_since_last_frame": None
                    if cs.last_frame_time is None
                    else round(now - cs.last_frame_time, 3),
                    "connected_seconds": None
                    if cs.connected_since is None or not cs.connected
                    else round(now - cs.connected_since, 1),
                    "reconnect_count": cs.reconnect_count,
                    "dropped_frames": cs.dropped_frames,
                    "decode_errors": cs.decode_errors,
                    "last_error": redact_sensitive(cs.last_error),
                    "ai_processed_frames": stats.camera_ai_processed_frames.get(camera.camera_id, 0),
                    "ai_fps": stats.camera_ai_fps.get(camera.camera_id, 0.0),
                    "detection_confidence": stats.camera_detection_confidence.get(camera.camera_id),
                    "frames_received": capture._frame_id,
                    "frames_processed": stats.camera_processed_frames.get(camera.camera_id, 0),
                    "detections": stats.camera_person_detections.get(camera.camera_id, 0),
                    "confirmed_tracks": stats.camera_confirmed_tracks.get(camera.camera_id, 0),
                    "inference_status": stats.camera_inference_status.get(camera.camera_id, "waiting for frame"),
                    "inference_latency_ms": stats.camera_inference_latency_ms.get(camera.camera_id),
                    "reid_status": stats.reid_status,
                    "rejected_events": self.pipeline.counters[camera.camera_id].rejected_events,
                    "last_rejection_reason": self.pipeline.counters[camera.camera_id].last_rejection_reason,
                    "rejection_counts": self.pipeline.counters[camera.camera_id].rejection_counts,
                    "consensus_rejected_events": stats.camera_consensus_rejections.get(camera.camera_id, 0),
                    "last_consensus_rejection_reason": stats.camera_last_consensus_reason.get(camera.camera_id, ""),
                    "ai_raw_person_detections": stats.camera_raw_person_detections.get(camera.camera_id, 0),
                    "ai_person_detections": stats.camera_person_detections.get(camera.camera_id, 0),
                    "ai_confirmed_tracks": stats.camera_confirmed_tracks.get(camera.camera_id, 0),
                    "seconds_since_last_ai_frame": (
                        round(now - stats.camera_last_processed_time[camera.camera_id], 2)
                        if camera.camera_id in stats.camera_last_processed_time
                        else None
                    ),
                    "obstructed": stats.camera_obstructed.get(camera.camera_id, False),
                    "obstruction_reason": stats.camera_obstruction_reason.get(camera.camera_id, ""),
                    "visible": self.pipeline.counters[camera.camera_id].counts.visible,
                    "entered": self.pipeline.counters[camera.camera_id].counts.entered,
                    "exited": self.pipeline.counters[camera.camera_id].counts.exited,
                }
            )

        payload = {
            "timestamp": now,
            "counts": {
                "inside": counts.inside,
                "entered": counts.entered,
                "exited": counts.exited,
                "visible": stats.global_visible,
                "suppressed": counts.suppressed_duplicates,
                "uncertain": counts.uncertain_consensus,
                "daily_unique": counts.daily_unique,
                "daily_unique_degraded": counts.daily_unique_degraded,
                "throughput": counts.throughput,
                "wrong_way": counts.wrong_way,
                "last_event_time": stats.last_detection_at,
            },
            "cameras": cameras,
            "runtime": {
                **read_host_metrics(),
                "latency": {k: {"mean_ms": v.mean_ms, "p95_ms": v.p95_ms} for k, v in stats.latency.items()},
                "inference_fps": round(stats.inference_fps, 1),
                "detector_enabled": self.config.model.detector_enabled,
                "detector_active": stats.detector_active,
                "reid_enabled": self.config.model.reid_required,
                "hailo_latency_ms": round(stats.inference_latency_ms, 1),
                "total_latency_ms": round(stats.total_latency_ms, 1),
                "frame_age_ms": round(stats.frame_age_ms, 1),
                "hailo_status": stats.hailo_status,
                "detector_error": redact_sensitive(stats.detector_error),
                "hailo_device": stats.hailo_device,
                "hailo_inference_count": stats.hailo_inference_count,
                "active_hef": stats.active_hef,
                "reid_status": stats.reid_status,
                "reid_inference_count": stats.reid_inference_count,
                "reid_latency_ms": round(stats.reid_latency_ms, 1),
                "reid_cache_size": stats.reid_cache_size,
                "queue_length": stats.queue_length,
            },
        }
        self.live_status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.live_status_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        tmp.replace(self.live_status_path)
        try:
            self.live_status_path.chmod(0o600)
        except OSError:
            pass


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="PersonenZähler background service")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--system-layout", action="store_true")
    args = parser.parse_args()
    paths = RuntimePaths.discover(
        args.project_root.resolve(), system_layout=args.system_layout
    )
    configure_logging(paths.log_dir)
    service = VisitorCounterService(paths)

    def request_stop(_signum: int, _frame: object) -> None:
        service.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    return service.run()


if __name__ == "__main__":
    raise SystemExit(main())
