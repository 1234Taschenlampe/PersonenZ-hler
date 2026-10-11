from __future__ import annotations

import logging
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from time import monotonic
from typing import Callable

import cv2

from .camera_manager import LatestFrameHub
from .configuration import AppConfig
from .counter import GlobalCounts, LineCrossingCounter
from .data_protection import load_data_protector
from .database import EventDatabase
from .dual_camera_consensus import DualCameraConsensus
from .hailo_manager import HailoManager, HailoUnavailableError
from .identity_manager import GlobalIdentityManager
from .model_manager import ModelManager, ModelUnavailableError
from .obstruction import CameraObstructionDetector
from .privacy import anonymize_frame, hidden_preview
from .reid_manager import OSNetReIDManager
from .tracker import create_tracker
from .types import (
    ConsensusDecision,
    CountingLine,
    Detection,
    FramePacket,
    LatencyWindow,
    RuntimeStats,
    TrackedObject,
)

LOGGER = logging.getLogger(__name__)

FrameCallback = Callable[[str, object, list[TrackedObject]], None]
StatsCallback = Callable[[RuntimeStats, GlobalCounts], None]


@dataclass
class _LivePresenceMemory:
    first_seen_at: float
    last_seen_at: float
    frames_seen: int = 0
    counted_inside: bool = False


class ProcessingPipeline(Thread):
    def __init__(
        self,
        config: AppConfig,
        project_root: Path,
        input_queue: LatestFrameHub,
        stop_event: Event,
        frame_callback: FrameCallback | None = None,
        stats_callback: StatsCallback | None = None,
    ) -> None:
        super().__init__(daemon=True, name="inference-pipeline")
        self.config = config
        self.project_root = project_root
        self.input_queue = input_queue
        self.stop_event = stop_event
        self.frame_callback = frame_callback
        self.stats_callback = stats_callback
        self.runtime_stats = RuntimeStats()
        self._camera_ai_ticks: dict[str, deque[float]] = {}
        self.latency_window = LatencyWindow()
        self.global_counts = GlobalCounts()
        self.model = ModelManager(config.model, project_root)
        protector = load_data_protector(config.database, project_root)
        self.database = EventDatabase(
            project_root / config.database.path,
            store_personal_events=config.database.store_events,
            retention_hours=config.database.retention_hours,
            protector=protector,
            require_encryption=config.database.encryption_required,
        )
        self._restore_counts()
        self.consensus = DualCameraConsensus(config.consensus)
        self.reid = OSNetReIDManager(config.model, project_root)
        self.identity = GlobalIdentityManager(
            config.identity, cross_camera_matching=config.model.reid_required
        )
        self.trackers = {
            camera_id: create_tracker(config.tracking)[0]
            for camera_id in config.cameras
        }
        self.tracker_status = create_tracker(config.tracking)[1]
        self.obstruction_detectors = {
            camera_id: CameraObstructionDetector() for camera_id in config.cameras
        }
        self.counters = {
            camera_id: LineCrossingCounter(
                camera_id,
                CountingLine(
                    camera.line_start, camera.line_end, camera.in_positive_side
                ),
                config.tracking,
                camera,
            )
            for camera_id, camera in config.cameras.items()
        }
        self.hailo = HailoManager(config.model, self.model.hef_path)
        self._camera_order = list(config.cameras)
        self._last_camera_id: str | None = None
        self._max_frame_age_seconds = 0.50
        self._gui_interval_seconds = 1.0 / 15.0
        self._next_gui_emit_at: dict[str, float] = {
            camera_id: 0.0 for camera_id in config.cameras
        }
        self._reid_cache: dict[tuple[str, int], tuple[float, tuple[float, ...]]] = {}
        self._inside_global_person_ids: set[int] = set()
        self._live_presence: dict[int, _LivePresenceMemory] = {}
        self._last_persisted_global_counts: tuple[int, int, int, int] | None = None
        self._last_retention_purge_at = 0.0
        self._state_lock = RLock()
        self._cache_lock = Lock()
        self._shared_hailo_lock = Lock()
        self._shared_reid_lock = Lock()
        self._hailo_workers = {camera_id: self.hailo for camera_id in config.cameras}
        self._reid_workers = {camera_id: self.reid for camera_id in config.cameras}
        self._camera_hailo_stage_ms: dict[str, dict[str, float]] = {}
        self._camera_hailo_latency_ms: dict[str, float] = {}

    def run(self) -> None:
        LOGGER.info("Starting processing pipeline")
        if not self.config.model.detector_enabled:
            self.runtime_stats.detector_active = False
            self.runtime_stats.hailo_status = "paused"
            self.runtime_stats.reid_status = "OSNet paused (YOLO disabled)"
            LOGGER.info("YOLO detection paused by user; camera status stays available")
            self.runtime_stats.parallel_inference_mode = "parallel_camera_workers_no_detector"
        else:
            try:
                model_status = self.model.require_available()
                self.runtime_stats.active_hef = str(model_status.path)
                self.runtime_stats.active_hef_sha256 = model_status.sha256
                self.runtime_stats.model_type = model_status.model_type
                if self.config.model.reid_required:
                    reid_status = self.reid.require_available(validate_hailo=True)
                    self.runtime_stats.reid_status = reid_status.message
                    self.runtime_stats.reid_hef_sha256 = reid_status.sha256
                else:
                    self.runtime_stats.reid_status = "OSNet ReID disabled by configuration"
                    self.runtime_stats.reid_hef_sha256 = ""
                self.hailo.initialize()
                if self.config.model.reid_required:
                    self.reid.initialize()
                    self.runtime_stats.reid_status = self.reid.status_message
                self.runtime_stats.hailo_status = self.hailo.status
                self.runtime_stats.hailo_architecture = self.hailo.hailo_architecture
                self.runtime_stats.hailo_device = self.hailo.hailo_device
                self.runtime_stats.backend = self.hailo.backend
                self.runtime_stats.detector_active = True
                self._initialize_parallel_engines()
            except (HailoUnavailableError, ModelUnavailableError, FileNotFoundError) as exc:
                self.runtime_stats.hailo_status = str(exc)
                self.runtime_stats.detector_error = str(exc)
                LOGGER.error("Processing pipeline cannot start: %s", exc)
                self._emit_stats()
                self.hailo.close()
                self.reid.close()
                self.database.close()
                return
        frames = 0
        tick = monotonic()
        status_tick = 0.0
        try:
            with ThreadPoolExecutor(max_workers=max(1, len(self._camera_order)), thread_name_prefix="inference-camera") as pool:
                pending: dict[str, Future[None]] = {}
                deferred_packet: FramePacket | None = None
                while not self.stop_event.is_set():
                    for camera_id, future in list(pending.items()):
                        if future.done():
                            del pending[camera_id]
                            try:
                                future.result()
                            except Exception:
                                LOGGER.exception("CAMERA_WORKER_FAILED camera=%s", camera_id)
                                self.stop_event.set()
                                break
                            frames += 1
                    if self.stop_event.is_set():
                        break
                    available = [cam for cam in self._camera_order if cam not in pending]
                    if available and (deferred_packet is None or deferred_packet.camera_id in available):
                        packet = deferred_packet
                        deferred_packet = None
                        if packet is None:
                            packet = self.input_queue.get_next(
                                available, self._last_camera_id, timeout=0.05,
                                max_age_seconds=self._max_frame_age_seconds,
                            )
                        if packet is not None:
                            if packet.camera_id in available:
                                self._last_camera_id = packet.camera_id
                                pending[packet.camera_id] = pool.submit(self._process_packet, packet)
                            else:
                                # A custom queue adapter might ignore camera_order.
                                # Hold its packet instead of dropping a countable frame.
                                deferred_packet = packet
                                LOGGER.debug("CAMERA_QUEUE_DEFERRED camera=%s", packet.camera_id)
                    elif pending:
                        wait(tuple(pending.values()), timeout=0.05, return_when=FIRST_COMPLETED)
                    now = monotonic()
                    if now - tick >= 1.0:
                        with self._state_lock:
                            self.runtime_stats.inference_fps = frames / max(0.001, now - tick)
                        frames, tick = 0, now
                    if now - status_tick >= 0.2:
                        with self._state_lock:
                            self._run_timeout_check()
                            self._update_queue_stats()
                            self._emit_stats()
                        status_tick = now
                for camera_id, future in pending.items():
                    try:
                        future.result()
                    except Exception:
                        LOGGER.exception("CAMERA_WORKER_FAILED_ON_STOP camera=%s", camera_id)
                with self._state_lock:
                    self._update_queue_stats()
                    self._emit_stats()
        finally:
            for engine in self._unique_engines(self._hailo_workers):
                engine.close()
            for engine in self._unique_engines(self._reid_workers):
                engine.close()
            self.database.close()
            LOGGER.info("Processing pipeline stopped")

    @staticmethod
    def _unique_engines(engines: dict[str, object]) -> list[object]:
        return list({id(value): value for value in engines.values()}.values())

    @classmethod
    def _total_engine_inferences(cls, engines: dict[str, object]) -> int:
        return sum(value.inference_count for value in cls._unique_engines(engines))

    def _initialize_parallel_engines(self) -> None:
        if len(self._camera_order) < 2:
            self.runtime_stats.parallel_inference_mode = "single_camera"
            return
        detector_parallel = True
        reid_parallel = not self.config.model.reid_required
        for camera_id in self._camera_order[1:]:
            extra = HailoManager(self.config.model, self.model.hef_path)
            try:
                extra.initialize()
            except Exception as exc:
                extra.close()
                detector_parallel = False
                LOGGER.warning("PARALLEL_HAILO_FALLBACK camera=%s exception=%s", camera_id, type(exc).__name__)
            else:
                self._hailo_workers[camera_id] = extra
            if self.config.model.reid_required:
                second_reid = OSNetReIDManager(self.config.model, self.project_root)
                try:
                    second_reid.initialize()
                except Exception as exc:
                    second_reid.close()
                    LOGGER.warning("PARALLEL_OSNET_FALLBACK camera=%s exception=%s", camera_id, type(exc).__name__)
                else:
                    self._reid_workers[camera_id] = second_reid
        if self.config.model.reid_required:
            reid_parallel = len(self._unique_engines(self._reid_workers)) == len(self._camera_order)
        self.runtime_stats.parallel_inference_mode = (
            "parallel_hailo_and_osnet" if detector_parallel and reid_parallel
            else "parallel_camera_workers_serialized_shared_models"
        )
        LOGGER.info("CAMERA_PIPELINE_MODE %s", self.runtime_stats.parallel_inference_mode)

    def _process_packet(self, packet: FramePacket) -> None:
        started = monotonic()
        stage_ms: dict[str, float] = {
            "frame_age_at_dequeue_ms": (started - packet.monotonic_time) * 1000.0,
        }
        obstruction_start = monotonic()
        obstruction = self.obstruction_detectors[packet.camera_id].update(
            packet.image
        )
        stage_ms["obstruction_ms"] = (monotonic() - obstruction_start) * 1000.0
        self.runtime_stats.camera_obstructed[packet.camera_id] = (
            obstruction.obstructed
        )
        self.runtime_stats.camera_obstruction_reason[packet.camera_id] = obstruction.reason
        detect_start = monotonic()
        raw_detections = [] if obstruction.obstructed else self._detect(packet)
        if obstruction.obstructed:
            self.runtime_stats.camera_inference_status[packet.camera_id] = "obstructed"
        detections = self._filter_person_detections(
            raw_detections, packet.width, packet.height
        )
        self.runtime_stats.camera_raw_person_detections[packet.camera_id] = len(raw_detections)
        self.runtime_stats.camera_person_detections[packet.camera_id] = len(detections)
        self.runtime_stats.camera_detection_confidence[packet.camera_id] = max(
            (d.confidence for d in detections), default=None
        )
        stage_ms["detect_total_ms"] = (monotonic() - detect_start) * 1000.0
        stage_ms.update(self._camera_hailo_stage_ms.get(packet.camera_id, self.hailo.last_stage_ms))
        self.runtime_stats.camera_inference_latency_ms[packet.camera_id] = (
            self._camera_hailo_latency_ms.get(packet.camera_id, self.hailo.last_latency_ms)
            if self.runtime_stats.camera_inference_status.get(packet.camera_id) == "active"
            else None
        )
        tracker_start = monotonic()
        tracks = self.trackers[packet.camera_id].update(
            packet.camera_id, detections
        )
        stage_ms["tracker_ms"] = (monotonic() - tracker_start) * 1000.0
        observed_tracks = self._filter_live_count_tracks(
            tracks, packet.width, packet.height, confirmed_only=False
        )
        countable_tracks = [track for track in observed_tracks if track.confirmed]
        tentative_tracks = [track for track in observed_tracks if not track.confirmed]
        reid_start = monotonic()
        tracks = self._with_reid_embeddings(packet, countable_tracks)
        stage_ms["osnet_reid_ms"] = (monotonic() - reid_start) * 1000.0
        with self._state_lock:
            identity_start = monotonic()
            tracks = self.identity.update(
                packet.camera_id,
                tracks,
                packet.captured_at,
                packet.width,
                packet.height,
            )
            stage_ms["identity_ms"] = (monotonic() - identity_start) * 1000.0
            self.runtime_stats.camera_confirmed_tracks[packet.camera_id] = sum(
                track.confirmed and track.lost_frames == 0 for track in tracks
            )
            self.runtime_stats.camera_processed_frames[packet.camera_id] = (
                self.runtime_stats.camera_processed_frames.get(packet.camera_id, 0) + 1
            )
            self.runtime_stats.camera_last_processed_time[packet.camera_id] = packet.captured_at
            visible_ids = {
                track.global_person_id
                for track in tracks
                if track.global_person_id is not None and track.lost_frames == 0
            }
            self.database.update_last_seen(visible_ids, packet.captured_at)
            self.global_counts.visible = self.identity.global_visible
            self.runtime_stats.global_visible = self.identity.global_visible
            self._sync_live_presence_counts(visible_ids, packet.captured_at)
            events = (
                []
                if obstruction.obstructed
                else self.counters[packet.camera_id].update(
                    packet.frame_id, tracks + tentative_tracks,
                    frame_size=(packet.width, packet.height)
                )
            )
            for event in events:
                decision = self.consensus.decide(event)
                if event.global_person_id is None:
                    decision = ConsensusDecision(
                        event,
                        False,
                        decision.duplicate_of,
                        True,
                        "missing global person id",
                    )

                self.database.record_decision(
                    decision,
                    self.config.model.model_name,
                    self.runtime_stats.total_latency_ms,
                )

                camera_num = 1 if packet.camera_id == "camera_1" else 2
                if decision.counted and not decision.uncertain:
                    LOGGER.info(
                        "COUNT_EVENT camera=%s direction=%s",
                        camera_num,
                        event.direction.value,
                    )
                else:
                    reason = decision.reason or "suppressed_or_uncertain"
                    self.runtime_stats.camera_consensus_rejections[packet.camera_id] = (
                        self.runtime_stats.camera_consensus_rejections.get(packet.camera_id, 0) + 1
                    )
                    self.runtime_stats.camera_last_consensus_reason[packet.camera_id] = reason
                    LOGGER.info(
                        "COUNT_REJECTED camera=%s reason=%s", camera_num, reason
                    )

                LOGGER.info(
                    "GUI_COUNTER_UPDATE global_inside=%s global_entries=%s global_exits=%s",
                    self.global_counts.inside,
                    self.global_counts.entered,
                    self.global_counts.exited,
                )
        draw_start = monotonic()
        gui_start = monotonic()
        if (
            self.frame_callback
            and gui_start >= self._next_gui_emit_at[packet.camera_id]
        ):
            annotated = self._annotate(packet, tracks)
            self.frame_callback(packet.camera_id, annotated, tracks)
            self._next_gui_emit_at[packet.camera_id] = (
                gui_start + self._gui_interval_seconds
            )
        stage_ms["draw_boxes_ms"] = (monotonic() - draw_start) * 1000.0
        stage_ms["gui_transfer_ms"] = (monotonic() - gui_start) * 1000.0

        now = monotonic()
        with self._state_lock:
            self.runtime_stats.total_latency_ms = (now - packet.monotonic_time) * 1000.0
            stage_ms["processing_total_ms"] = (now - started) * 1000.0
            stage_ms["end_to_end_ms"] = self.runtime_stats.total_latency_ms
            self.latency_window.add(stage_ms)
            self.runtime_stats.latency = self.latency_window.summaries()
            self.runtime_stats.frame_age_ms = stage_ms["frame_age_at_dequeue_ms"]
            self.runtime_stats.inference_latency_ms = self._camera_hailo_latency_ms.get(
                packet.camera_id, self.hailo.last_latency_ms
            )
            self.runtime_stats.hailo_inference_count = self._total_engine_inferences(self._hailo_workers)
            self.runtime_stats.reid_inference_count = self._total_engine_inferences(self._reid_workers)
            self.runtime_stats.reid_latency_ms = self._reid_workers[packet.camera_id].last_latency_ms
            self.runtime_stats.reid_cache_size = len(self._reid_cache)

    def _with_reid_embeddings(
        self, packet: FramePacket, tracks: list[TrackedObject]
    ) -> list[TrackedObject]:
        manager = self._reid_workers.get(packet.camera_id, self.reid)
        if not self.config.model.reid_required or not manager.ready:
            return tracks
        now = monotonic()
        updated: list[TrackedObject] = []
        interval = max(0.1, self.config.identity.reid_update_interval_seconds)
        ttl = max(interval, self.config.identity.cache_ttl_seconds)
        with self._cache_lock:
            for key, (seen_at, _) in list(self._reid_cache.items()):
                if now - seen_at > ttl:
                    self._reid_cache.pop(key, None)
        shared = sum(value is manager for value in self._reid_workers.values()) > 1
        for track in tracks:
            if not track.confirmed or track.lost_frames != 0:
                updated.append(track)
                continue
            key = (packet.camera_id, track.track_id)
            with self._cache_lock:
                cached = self._reid_cache.get(key)
            if cached and now - cached[0] < interval:
                with self._shared_reid_lock if shared else nullcontext():
                    manager.cache_hits += 1
                updated.append(replace(track, embedding=cached[1], last_reid_at=cached[0]))
                continue
            # Per-camera contexts execute in parallel. Only a shared fallback
            # OSNet context is protected from concurrent HailoRT calls.
            with self._shared_reid_lock if shared else nullcontext():
                embedding = manager.infer_embedding(packet.image, track.bbox)
            if embedding is None:
                updated.append(track)
                continue
            with self._cache_lock:
                self._reid_cache[key] = (now, embedding)
            updated.append(replace(track, embedding=embedding, last_reid_at=now))
        return updated

    def _update_queue_stats(self) -> None:
        self.runtime_stats.queue_length = self.input_queue.qsize()
        self.runtime_stats.queue_fill = self.runtime_stats.queue_length / max(
            self.input_queue.maxsize, 1
        )
        self.runtime_stats.dropped_frames = self.input_queue.dropped_counts()

    def reset_counts(self) -> None:
        with self._state_lock:
            for counter in self.counters.values():
                counter.reset()
            self.consensus.reset()
            self.identity.reset()
            self.database.reset_global_counts()
            self.global_counts = GlobalCounts()
            self._inside_global_person_ids.clear()
            self._live_presence.clear()
            self._last_persisted_global_counts = None

    def _sync_live_presence_counts(
        self, visible_ids: set[int], timestamp: float
    ) -> None:
        for global_id in visible_ids:
            memory = self._live_presence.get(global_id)
            if memory is None:
                memory = _LivePresenceMemory(
                    first_seen_at=timestamp, last_seen_at=timestamp
                )
                self._live_presence[global_id] = memory
            memory.frames_seen += 1
            memory.last_seen_at = timestamp
            if (
                memory.counted_inside
                or memory.frames_seen < self.config.identity.live_entry_min_frames
            ):
                continue
            memory.counted_inside = True
            self._inside_global_person_ids.add(global_id)
            self.global_counts.entered += 1
            LOGGER.info(
                "LIVE_GLOBAL_COUNTER event=entry inside=%s entered_total=%s",
                len(self._inside_global_person_ids),
                self.global_counts.entered,
            )

        exited: list[int] = []
        grace = max(0.1, self.config.identity.live_exit_grace_seconds)
        for global_id, memory in list(self._live_presence.items()):
            if global_id in visible_ids:
                continue
            if timestamp - memory.last_seen_at <= grace:
                continue
            if memory.counted_inside and global_id in self._inside_global_person_ids:
                self._inside_global_person_ids.remove(global_id)
                self.global_counts.exited += 1
                exited.append(global_id)
            del self._live_presence[global_id]

        self.global_counts.inside = len(self._inside_global_person_ids)
        if exited:
            LOGGER.info(
                "LIVE_GLOBAL_COUNTER event=exit count=%s inside=%s exited_total=%s",
                len(exited),
                self.global_counts.inside,
                self.global_counts.exited,
            )
        self._persist_global_counts()

    def _persist_global_counts(self) -> None:
        snapshot = (
            self.global_counts.entered,
            self.global_counts.exited,
            self.global_counts.inside,
            self.global_counts.wrong_way,
        )
        if snapshot == getattr(self, "_last_persisted_global_counts", None):
            return
        database = getattr(self, "database", None)
        if database is None:
            self._last_persisted_global_counts = snapshot
            return
        self.database.set_global_counts(*snapshot)
        self._last_persisted_global_counts = snapshot

    def _filter_person_detections(
        self, detections: list[Detection], frame_width: int, frame_height: int
    ) -> list[Detection]:
        filtered: list[Detection] = []
        for detection in detections:
            if detection.class_id != 0 or detection.label != "person":
                continue
            if detection.confidence < self.config.identity.live_min_confidence:
                continue
            if not self._bbox_is_person_like(detection.bbox, frame_width, frame_height):
                continue
            filtered.append(detection)
        return filtered

    def _filter_live_count_tracks(
        self, tracks: list[TrackedObject], frame_width: int, frame_height: int,
        *, confirmed_only: bool = True,
    ) -> list[TrackedObject]:
        return [
            track
            for track in tracks
            if (track.confirmed or not confirmed_only)
            and track.lost_frames == 0
            and track.confidence >= self.config.identity.live_min_confidence
            and self._bbox_is_person_like(track.bbox, frame_width, frame_height)
        ]

    def _bbox_is_person_like(self, bbox, frame_width: int, frame_height: int) -> bool:
        if bbox.area < max(
            self.config.tracking.minimum_bbox_area,
            self.config.identity.live_min_bbox_area,
        ):
            return False
        if bbox.width < 8 or bbox.height < 24:
            return False
        if (
            bbox.x2 <= 0
            or bbox.y2 <= 0
            or bbox.x1 >= frame_width
            or bbox.y1 >= frame_height
        ):
            return False
        aspect_ratio = bbox.width / max(bbox.height, 1.0)
        return (
            self.config.identity.live_min_aspect_ratio
            <= aspect_ratio
            <= self.config.identity.live_max_aspect_ratio
        )

    def _restore_counts(self) -> None:
        restored = self.database.restore_counts()
        self.global_counts.inside = restored["inside"]
        self.global_counts.entered = restored["entered"]
        self.global_counts.exited = restored["exited"]
        self.global_counts.timeouts = restored["timeouts"]
        self.global_counts.uncertain_consensus = restored["uncertain"]
        self.global_counts.suppressed_duplicates = restored["suppressed"]
        self.global_counts.wrong_way = restored["wrong_way"]
        self.runtime_stats.timeouts = restored["timeouts"]

    def _restore_inside_only(self) -> None:
        restored = self.database.restore_counts()
        self.global_counts.inside = restored["inside"]
        self.global_counts.timeouts = restored["timeouts"]
        self.runtime_stats.timeouts = restored["timeouts"]

    def _run_timeout_check(self) -> None:
        now = monotonic()
        if now - self._last_retention_purge_at >= 300.0:
            self.database.purge_expired()
            self._last_retention_purge_at = now
        if not self.config.timeout.presence_timeout_enabled:
            return
        result = self.database.close_timed_out_sessions(
            self.config.timeout.presence_timeout_minutes
        )
        if result.closed_sessions:
            self.global_counts.timeouts += result.closed_sessions
            self._restore_inside_only()

    def _detect(self, packet: FramePacket) -> list[Detection]:
        if not self.config.model.detector_enabled:
            self.runtime_stats.camera_inference_status[packet.camera_id] = "paused"
            return []
        if not self.hailo.ready:
            self.runtime_stats.camera_inference_status[packet.camera_id] = "unavailable"
            self.runtime_stats.detector_active = False
            self.runtime_stats.detector_error = self.hailo.status
            return []
        try:
            manager = self._hailo_workers.get(packet.camera_id, self.hailo)
            shared = sum(value is manager for value in self._hailo_workers.values()) > 1
            # A separate HailoRT context per camera is preferred. A hardware
            # allocation failure falls back to serial calls on the shared one.
            try:
                with self._shared_hailo_lock if shared else nullcontext():
                    detections = manager.infer(packet.image)
                    self._camera_hailo_stage_ms[packet.camera_id] = dict(manager.last_stage_ms)
                    self._camera_hailo_latency_ms[packet.camera_id] = manager.last_latency_ms
            except HailoUnavailableError:
                if manager is self.hailo:
                    raise
                # A secondary context can fail after successful initialization,
                # e.g. following a firmware reset. Continue with the primary
                # configured model without killing either camera worker.
                LOGGER.warning("PARALLEL_HAILO_RUNTIME_FALLBACK camera=%s", packet.camera_id)
                manager.close()
                self._hailo_workers[packet.camera_id] = self.hailo
                self.runtime_stats.parallel_inference_mode = (
                    "parallel_camera_workers_serialized_shared_models"
                )
                with self._shared_hailo_lock:
                    detections = self.hailo.infer(packet.image)
                    self._camera_hailo_stage_ms[packet.camera_id] = dict(self.hailo.last_stage_ms)
                    self._camera_hailo_latency_ms[packet.camera_id] = self.hailo.last_latency_ms
            self.runtime_stats.camera_inference_status[packet.camera_id] = "active"
            self.runtime_stats.camera_ai_processed_frames[packet.camera_id] = (
                self.runtime_stats.camera_ai_processed_frames.get(packet.camera_id, 0) + 1
            )
            self._camera_ai_ticks.setdefault(packet.camera_id, deque(maxlen=120)).append(monotonic())
            self.runtime_stats.detector_active = True
            self.runtime_stats.detector_error = ""
            detections = [
                Detection(
                    bbox=detection.bbox,
                    confidence=detection.confidence,
                    class_id=detection.class_id,
                    label=detection.label,
                    camera_id=packet.camera_id,
                    timestamp=packet.captured_at,
                    model_name=self.config.model.model_name,
                    model_sha256=self.runtime_stats.active_hef_sha256,
                )
                for detection in detections
                if detection.class_id == 0 and detection.label == "person"
            ]
            self.runtime_stats.inference_latency_ms = self.hailo.last_latency_ms
            self.runtime_stats.hailo_inference_count = self._total_engine_inferences(self._hailo_workers)
            if detections:
                self.runtime_stats.last_detection_at = packet.captured_at

            if detections:
                LOGGER.debug(
                    "DETECTION camera=%s count=%s", packet.camera_id, len(detections)
                )
            return detections
        except HailoUnavailableError as exc:
            self.runtime_stats.camera_inference_status[packet.camera_id] = "error"
            self.runtime_stats.hailo_status = str(exc)
            self.runtime_stats.detector_active = False
            self.runtime_stats.detector_error = str(exc)
            LOGGER.error("Hailo inference failed: %s", exc)
            return []

    def _annotate(self, packet: FramePacket, tracks: list[TrackedObject]) -> object:
        image = packet.image.copy()
        if self.config.privacy.enabled:
            if (not self.config.display.show_camera_preview
                    and not self.config.privacy.video_stream_enabled):
                return hidden_preview(image)
            # Obscure sensitive image content BEFORE painting annotations.
            # Otherwise full-frame pixelation destroys the visible AI overlay.
            if self.config.display.anonymization_mode != "none":
                image = anonymize_frame(
                    image,
                    mode=self.config.display.anonymization_mode,
                    pixel_size=self.config.display.pixel_size,
                    tracks=tracks,
                )
        camera_config = self.config.cameras[packet.camera_id]
        sx = packet.width / max(1, camera_config.width)
        sy = packet.height / max(1, camera_config.height)
        scaled_start = (round(camera_config.line_start[0] * sx),
                        round(camera_config.line_start[1] * sy))
        scaled_end = (round(camera_config.line_end[0] * sx),
                      round(camera_config.line_end[1] * sy))
        role_text = f"KAMERA {packet.camera_id[-1]}"
        counts = self.counters[packet.camera_id].counts
        event_text = f"IN: {counts.entered}  OUT: {counts.exited}"
        cv2.rectangle(image, (0, 0), (330, 78), (0, 0, 0), -1)
        cv2.putText(
            image,
            role_text,
            (18, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            event_text,
            (18, 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        if camera_config.counting_mode == "exit_edge":
            # Two actual image boundaries, not an imaginary center line.
            # The configured line vector defines the A/B travel axis only.
            nx, ny = self.counters[packet.camera_id].normal_vector
            margin = round(camera_config.edge_margin_pixels * min(sx, sy))
            margin = max(3, margin)
            if abs(ny) >= abs(nx):
                edges = [
                    ((0, margin), (packet.width - 1, margin),
                     "A" if ny > 0 else "B"),
                    ((0, packet.height - margin - 1),
                     (packet.width - 1, packet.height - margin - 1),
                     "B" if ny > 0 else "A"),
                ]
            else:
                edges = [
                    ((margin, 0), (margin, packet.height - 1),
                     "A" if nx > 0 else "B"),
                    ((packet.width - margin - 1, 0),
                     (packet.width - margin - 1, packet.height - 1),
                     "B" if nx > 0 else "A"),
                ]
            for first, second, side in edges:
                transition = "A_to_B" if side == "B" else "B_to_A"
                marker = "+1 IN" if transition == camera_config.entry_direction else "-1 OUT"
                color = (0, 230, 100) if marker.startswith("+") else (0, 160, 255)
                cv2.line(image, first, second, color, 3, cv2.LINE_AA)
                label_x = min(packet.width - 120, max(10, first[0] + 10))
                label_y = min(packet.height - 10, max(100, first[1] + 25))
                cv2.putText(image, marker, (label_x, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
        else:
            cv2.line(image, scaled_start, scaled_end, (0, 220, 255), 3)
            # The legacy mode displays the middle line and hysteresis bounds.
            ax, ay = scaled_start
            bx, by = scaled_end
            line_length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            if line_length > 0:
                nx = -(by - ay) / line_length
                ny = (bx - ax) / line_length
                d = self.config.tracking.zone_hysteresis_pixels * min(sx, sy)
                cv2.line(image,
                         (int(ax - nx * d), int(ay - ny * d)),
                         (int(bx - nx * d), int(by - ny * d)),
                         (0, 0, 255), 1, cv2.LINE_AA)
                cv2.line(image,
                         (int(ax + nx * d), int(ay + ny * d)),
                         (int(bx + nx * d), int(by + ny * d)),
                         (0, 255, 0), 1, cv2.LINE_AA)

        for track in tracks:
            box = track.bbox
            cv2.rectangle(
                image,
                (int(box.x1), int(box.y1)),
                (int(box.x2), int(box.y2)),
                (0, 255, 120),
                2,
            )

            counter = self.counters[packet.camera_id]
            memory = counter._tracks.get(track.track_id)
            zone_text = memory.stable_zone if memory else "neutral"
            counted_text = "ja" if (memory and memory.counted) else "nein"
            # Each door supports both directions; location is not a direction.
            dir_text = "IN/OUT"

            label = f"ID:{track.track_id} Z:{zone_text} R:{dir_text} C:{counted_text}"
            cv2.putText(
                image,
                label,
                (int(box.x1), max(0, int(box.y1) - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 120),
                2,
                cv2.LINE_AA,
            )
        return image

    def _emit_stats(self) -> None:
        now = monotonic()
        for camera_id, ticks in self._camera_ai_ticks.items():
            while ticks and now - ticks[0] >= 1.0:
                ticks.popleft()
            self.runtime_stats.camera_ai_fps[camera_id] = float(len(ticks))
        if self.stats_callback:
            self.stats_callback(self.runtime_stats, self.global_counts)

            # Log GUI_COUNTER_UPDATE periodically (once per second)
            now = monotonic()
            if (
                not hasattr(self, "_last_gui_log_time")
                or now - self._last_gui_log_time >= 1.0
            ):
                LOGGER.info(
                    "GUI_COUNTER_UPDATE global_inside=%s global_entries=%s global_exits=%s",
                    self.global_counts.inside,
                    self.global_counts.entered,
                    self.global_counts.exited,
                )
                self._last_gui_log_time = now
