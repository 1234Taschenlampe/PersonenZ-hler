from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Thread
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
from .types import ConsensusDecision, CountingLine, Detection, FramePacket, LatencyWindow, RuntimeStats, TrackedObject

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
        self.identity = GlobalIdentityManager(config.identity)
        self.trackers = {camera_id: create_tracker(config.tracking)[0] for camera_id in config.cameras}
        self.tracker_status = create_tracker(config.tracking)[1]
        self.obstruction_detectors = {camera_id: CameraObstructionDetector() for camera_id in config.cameras}
        self.counters = {
            camera_id: LineCrossingCounter(
                camera_id,
                CountingLine(camera.line_start, camera.line_end, camera.in_positive_side),
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
        self._next_gui_emit_at: dict[str, float] = {camera_id: 0.0 for camera_id in config.cameras}
        self._reid_cache: dict[tuple[str, int], tuple[float, tuple[float, ...]]] = {}
        self._inside_global_person_ids: set[int] = set()
        self._live_presence: dict[int, _LivePresenceMemory] = {}
        self._last_persisted_global_counts: tuple[int, int, int] | None = None
        self._last_retention_purge_at = 0.0

    def run(self) -> None:
        LOGGER.info("Starting processing pipeline")
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
        except (HailoUnavailableError, ModelUnavailableError, FileNotFoundError) as exc:
            self.runtime_stats.hailo_status = str(exc)
            self.runtime_stats.detector_error = str(exc)
            LOGGER.error("Processing pipeline cannot start: %s", exc)
            self._emit_stats()
            self.database.close()
            return
        frames = 0
        last_tick = monotonic()
        while not self.stop_event.is_set():
            packet = self.input_queue.get_next(
                self._camera_order,
                self._last_camera_id,
                timeout=0.2,
                max_age_seconds=self._max_frame_age_seconds,
            )
            if packet is None:
                self._run_timeout_check()
                self._update_queue_stats()
                self._emit_stats()
                continue
            started = monotonic()
            self._last_camera_id = packet.camera_id
            stage_ms: dict[str, float] = {
                "frame_age_at_dequeue_ms": (started - packet.monotonic_time) * 1000.0,
            }
            obstruction_start = monotonic()
            obstruction = self.obstruction_detectors[packet.camera_id].update(packet.image)
            stage_ms["obstruction_ms"] = (monotonic() - obstruction_start) * 1000.0
            self.runtime_stats.camera_obstructed[packet.camera_id] = obstruction.obstructed
            detect_start = monotonic()
            detections = [] if obstruction.obstructed else self._detect(packet)
            detections = self._filter_person_detections(detections, packet.width, packet.height)
            stage_ms["detect_total_ms"] = (monotonic() - detect_start) * 1000.0
            stage_ms.update(self.hailo.last_stage_ms)
            tracker_start = monotonic()
            tracks = self.trackers[packet.camera_id].update(packet.camera_id, detections)
            stage_ms["tracker_ms"] = (monotonic() - tracker_start) * 1000.0
            countable_tracks = self._filter_live_count_tracks(tracks, packet.width, packet.height)
            reid_start = monotonic()
            tracks = self._with_reid_embeddings(packet, countable_tracks)
            stage_ms["osnet_reid_ms"] = (monotonic() - reid_start) * 1000.0
            identity_start = monotonic()
            tracks = self.identity.update(packet.camera_id, tracks, packet.captured_at, packet.width, packet.height)
            stage_ms["identity_ms"] = (monotonic() - identity_start) * 1000.0
            visible_ids = {track.global_person_id for track in tracks if track.global_person_id is not None and track.lost_frames == 0}
            self.database.update_last_seen(visible_ids, packet.captured_at)
            self.global_counts.visible = self.identity.global_visible
            self.runtime_stats.global_visible = self.identity.global_visible
            self._sync_live_presence_counts(visible_ids, packet.captured_at)
            events = [] if obstruction.obstructed else self.counters[packet.camera_id].update(packet.frame_id, tracks)
            for event in events:
                decision = self.consensus.decide(event)
                if event.global_person_id is None:
                    decision = ConsensusDecision(event, False, decision.duplicate_of, True, "missing global person id")
                
                self.database.record_decision(decision, self.config.model.model_name, self.runtime_stats.total_latency_ms)
                
                camera_num = 1 if packet.camera_id == "camera_1" else 2
                if decision.counted and not decision.uncertain:
                    LOGGER.info("COUNT_EVENT camera=%s direction=%s", camera_num, event.direction.value)
                else:
                    reason = decision.reason or "suppressed_or_uncertain"
                    LOGGER.info("COUNT_REJECTED camera=%s reason=%s", camera_num, reason)
                
                LOGGER.info("GUI_COUNTER_UPDATE global_inside=%s global_entries=%s global_exits=%s",
                            self.global_counts.inside, self.global_counts.entered, self.global_counts.exited)
            draw_start = monotonic()
            annotated = self._annotate(packet, tracks)
            stage_ms["draw_boxes_ms"] = (monotonic() - draw_start) * 1000.0
            gui_start = monotonic()
            if self.frame_callback and gui_start >= self._next_gui_emit_at[packet.camera_id]:
                self.frame_callback(packet.camera_id, annotated, tracks)
                self._next_gui_emit_at[packet.camera_id] = gui_start + self._gui_interval_seconds
            stage_ms["gui_transfer_ms"] = (monotonic() - gui_start) * 1000.0
            frames += 1
            now = monotonic()
            self.runtime_stats.total_latency_ms = (now - packet.monotonic_time) * 1000.0
            stage_ms["processing_total_ms"] = (now - started) * 1000.0
            stage_ms["end_to_end_ms"] = self.runtime_stats.total_latency_ms
            self.latency_window.add(stage_ms)
            self.runtime_stats.latency = self.latency_window.summaries()
            self.runtime_stats.frame_age_ms = stage_ms["frame_age_at_dequeue_ms"]
            self.runtime_stats.inference_latency_ms = self.hailo.last_latency_ms
            self.runtime_stats.hailo_inference_count = self.hailo.inference_count
            self.runtime_stats.reid_inference_count = self.reid.inference_count
            self.runtime_stats.reid_latency_ms = self.reid.last_latency_ms
            self.runtime_stats.reid_cache_size = len(self._reid_cache)
            self._update_queue_stats()
            if now - last_tick >= 1.0:
                self.runtime_stats.inference_fps = frames / (now - last_tick)
                frames = 0
                last_tick = now
            self._run_timeout_check()
            self._emit_stats()
        self.hailo.close()
        self.reid.close()
        self.database.close()
        LOGGER.info("Processing pipeline stopped")

    def _with_reid_embeddings(self, packet: FramePacket, tracks: list[TrackedObject]) -> list[TrackedObject]:
        if not self.config.model.reid_required or not self.reid.ready:
            return tracks
        now = monotonic()
        updated: list[TrackedObject] = []
        interval = max(0.1, self.config.identity.reid_update_interval_seconds)
        ttl = max(interval, self.config.identity.cache_ttl_seconds)
        for key, (seen_at, _embedding) in list(self._reid_cache.items()):
            if now - seen_at > ttl:
                del self._reid_cache[key]
        for track in tracks:
            if not track.confirmed or track.lost_frames != 0:
                updated.append(track)
                continue
            key = (packet.camera_id, track.track_id)
            cached = self._reid_cache.get(key)
            if cached and now - cached[0] < interval:
                self.reid.cache_hits += 1
                updated.append(replace(track, embedding=cached[1], last_reid_at=cached[0]))
                continue
            embedding = self.reid.infer_embedding(packet.image, track.bbox)
            if embedding is None:
                updated.append(track)
                continue
            self._reid_cache[key] = (now, embedding)
            updated.append(replace(track, embedding=embedding, last_reid_at=now))
        return updated

    def _update_queue_stats(self) -> None:
        self.runtime_stats.queue_length = self.input_queue.qsize()
        self.runtime_stats.queue_fill = self.runtime_stats.queue_length / max(self.input_queue.maxsize, 1)
        self.runtime_stats.dropped_frames = self.input_queue.dropped_counts()

    def reset_counts(self) -> None:
        for counter in self.counters.values():
            counter.reset()
        self.consensus.reset()
        self.identity.reset()
        self.database.reset_global_counts()
        self.global_counts = GlobalCounts()
        self._inside_global_person_ids.clear()
        self._live_presence.clear()
        self._last_persisted_global_counts = None

    def _sync_live_presence_counts(self, visible_ids: set[int], timestamp: float) -> None:
        for global_id in visible_ids:
            memory = self._live_presence.get(global_id)
            if memory is None:
                memory = _LivePresenceMemory(first_seen_at=timestamp, last_seen_at=timestamp)
                self._live_presence[global_id] = memory
            memory.frames_seen += 1
            memory.last_seen_at = timestamp
            if memory.counted_inside or memory.frames_seen < self.config.identity.live_entry_min_frames:
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
        snapshot = (self.global_counts.entered, self.global_counts.exited, self.global_counts.inside)
        if snapshot == getattr(self, "_last_persisted_global_counts", None):
            return
        database = getattr(self, "database", None)
        if database is None:
            self._last_persisted_global_counts = snapshot
            return
        self.database.set_global_counts(*snapshot)
        self._last_persisted_global_counts = snapshot

    def _filter_person_detections(self, detections: list[Detection], frame_width: int, frame_height: int) -> list[Detection]:
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

    def _filter_live_count_tracks(self, tracks: list[TrackedObject], frame_width: int, frame_height: int) -> list[TrackedObject]:
        return [
            track
            for track in tracks
            if track.confirmed
            and track.lost_frames == 0
            and track.confidence >= self.config.identity.live_min_confidence
            and self._bbox_is_person_like(track.bbox, frame_width, frame_height)
        ]

    def _bbox_is_person_like(self, bbox, frame_width: int, frame_height: int) -> bool:
        if bbox.area < max(self.config.tracking.minimum_bbox_area, self.config.identity.live_min_bbox_area):
            return False
        if bbox.width < 8 or bbox.height < 24:
            return False
        if bbox.x2 <= 0 or bbox.y2 <= 0 or bbox.x1 >= frame_width or bbox.y1 >= frame_height:
            return False
        aspect_ratio = bbox.width / max(bbox.height, 1.0)
        return self.config.identity.live_min_aspect_ratio <= aspect_ratio <= self.config.identity.live_max_aspect_ratio

    def _restore_counts(self) -> None:
        restored = self.database.restore_counts()
        self.global_counts.inside = restored["inside"]
        self.global_counts.entered = restored["entered"]
        self.global_counts.exited = restored["exited"]
        self.global_counts.timeouts = restored["timeouts"]
        self.global_counts.uncertain_consensus = restored["uncertain"]
        self.global_counts.suppressed_duplicates = restored["suppressed"]
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
        result = self.database.close_timed_out_sessions(self.config.timeout.presence_timeout_minutes)
        if result.closed_sessions:
            self.global_counts.timeouts += result.closed_sessions
            self._restore_inside_only()

    def _detect(self, packet: FramePacket) -> list[Detection]:
        if not self.hailo.ready:
            return []
        try:
            detections = self.hailo.infer(packet.image)
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
            self.runtime_stats.hailo_inference_count = self.hailo.inference_count
            if detections:
                self.runtime_stats.last_detection_at = monotonic()
            
            if detections:
                LOGGER.debug("DETECTION camera=%s count=%s", packet.camera_id, len(detections))
            return detections
        except HailoUnavailableError as exc:
            self.runtime_stats.hailo_status = str(exc)
            LOGGER.error("Hailo inference failed: %s", exc)
            return []

    def _annotate(self, packet: FramePacket, tracks: list[TrackedObject]) -> object:
        image = packet.image.copy()
        camera_config = self.config.cameras[packet.camera_id]
        role_text = "EINGANG" if camera_config.role == "entrance" else "AUSGANG"
        event_text = "EINTRITT +1" if camera_config.role == "entrance" else "AUSTRITT -1"
        cv2.rectangle(image, (0, 0), (330, 78), (0, 0, 0), -1)
        cv2.putText(image, role_text, (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(image, event_text, (18, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.line(image, camera_config.line_start, camera_config.line_end, (0, 220, 255), 2)
        
        # Draw Zone A and Zone B boundary lines based on normal vector and hysteresis
        ax, ay = camera_config.line_start
        bx, by = camera_config.line_end
        line_length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if line_length > 0:
            nx = -(by - ay) / line_length
            ny = (bx - ax) / line_length
            d = self.config.tracking.zone_hysteresis_pixels
            
            # Boundary A (distance < -d)
            ax_a = int(ax + nx * (-d))
            ay_a = int(ay + ny * (-d))
            bx_a = int(bx + nx * (-d))
            by_a = int(by + ny * (-d))
            cv2.line(image, (ax_a, ay_a), (bx_a, by_a), (0, 0, 255), 1, cv2.LINE_AA)
            
            # Boundary B (distance > d)
            ax_b = int(ax + nx * d)
            ay_b = int(ay + ny * d)
            bx_b = int(bx + nx * d)
            by_b = int(by + ny * d)
            cv2.line(image, (ax_b, ay_b), (bx_b, by_b), (0, 255, 0), 1, cv2.LINE_AA)

        for track in tracks:
            box = track.bbox
            cv2.rectangle(image, (int(box.x1), int(box.y1)), (int(box.x2), int(box.y2)), (0, 255, 120), 2)
            
            counter = self.counters[packet.camera_id]
            memory = counter._tracks.get(track.track_id)
            zone_text = memory.stable_zone if memory else "neutral"
            counted_text = "ja" if (memory and memory.counted) else "nein"
            dir_text = "IN" if camera_config.role == "entrance" else "OUT"
            
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
        if self.config.privacy.enabled:
            if not self.config.display.show_camera_preview and not self.config.privacy.video_stream_enabled:
                return hidden_preview(image)
            return anonymize_frame(
                image,
                mode=self.config.display.anonymization_mode,
                pixel_size=self.config.display.pixel_size,
                tracks=tracks,
            )
        return image

    def _emit_stats(self) -> None:
        if self.stats_callback:
            self.stats_callback(self.runtime_stats, self.global_counts)
            
            # Log GUI_COUNTER_UPDATE periodically (once per second)
            now = monotonic()
            if not hasattr(self, "_last_gui_log_time") or now - self._last_gui_log_time >= 1.0:
                LOGGER.info("GUI_COUNTER_UPDATE global_inside=%s global_entries=%s global_exits=%s",
                            self.global_counts.inside, self.global_counts.entered, self.global_counts.exited)
                self._last_gui_log_time = now
