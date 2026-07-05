from __future__ import annotations

import json
import logging
from pathlib import Path
import signal
import socket
import shutil
import subprocess
from threading import Event
from time import monotonic, sleep, time
from typing import Any

import cv2
import numpy as np
import psutil
from PySide6.QtCore import QPoint, QSocketNotifier, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .camera_manager import CameraCapture, CameraDeviceInfo, LatestFrameHub, discover_camera_devices, discover_cameras
from .configuration import AppConfig, load_config, save_config
from .counter import GlobalCounts
from .diagnostics import collect_diagnostics, read_pi_temperature_c
from .inference_pipeline import ProcessingPipeline
from .logging_setup import configure_logging
from .model_manager import ModelManager
from .reid_manager import OSNetReIDManager
from .types import FramePacket, RuntimeStats, TrackedObject
from .video_stream import FrameStreamExporter

LOGGER = logging.getLogger(__name__)


class CameraView(QLabel):
    line_changed = Signal(str, tuple, tuple)

    def __init__(self, camera_id: str) -> None:
        super().__init__()
        self.camera_id = camera_id
        self.setMinimumSize(420, 260)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#111; color:#ddd; border:1px solid #444;")
        self.setText(f"{camera_id}\nkein Kamerabild")
        self._pixmap: QPixmap | None = None
        self._line_start = QPoint(80, 180)
        self._line_end = QPoint(360, 180)
        self._drag: str | None = None

    def set_line(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self._line_start = QPoint(*start)
        self._line_end = QPoint(*end)
        self.update()

    def set_frame(self, frame: np.ndarray) -> None:
        if frame is None or frame.size == 0:
            raise ValueError(f"{self.camera_id}: empty frame")
        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            raise ValueError(f"{self.camera_id}: unsupported frame shape {frame.shape}")
        if frame.dtype != np.uint8:
            raise ValueError(f"{self.camera_id}: unsupported frame dtype {frame.dtype}")
        frame = np.ascontiguousarray(frame)
        if frame.shape[2] == 4:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(image)
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        if self._pixmap:
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        pen = QPen(Qt.yellow, 3)
        painter.setPen(pen)
        painter.drawLine(self._line_start, self._line_end)
        painter.setBrush(Qt.yellow)
        painter.drawEllipse(self._line_start, 6, 6)
        painter.drawEllipse(self._line_end, 6, 6)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (event.position().toPoint() - self._line_start).manhattanLength() < 18:
            self._drag = "start"
        elif (event.position().toPoint() - self._line_end).manhattanLength() < 18:
            self._drag = "end"

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag == "start":
            self._line_start = event.position().toPoint()
        elif self._drag == "end":
            self._line_end = event.position().toPoint()
        if self._drag:
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        _ = event
        if self._drag:
            self.line_changed.emit(
                self.camera_id,
                (self._line_start.x(), self._line_start.y()),
                (self._line_end.x(), self._line_end.y()),
            )
        self._drag = None


class MainWindow(QMainWindow):
    frame_ready = Signal(str, object, list)
    raw_frame_ready = Signal(str, object, int, float)
    stats_ready = Signal(object, object)

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.config_path = project_root / "config" / "config.yaml"
        self.config = load_config(self.config_path)
        configure_logging(project_root / "logs")
        self.setWindowTitle("YOLO26m Dual-Kamera Besucherzaehler")
        self.resize(1500, 900)
        self.frame_queue = LatestFrameHub(list(self.config.cameras))
        self.stop_event = Event()
        self.captures: list[CameraCapture] = []
        self.pipeline: ProcessingPipeline | None = None
        self.latest_raw_frames: dict[str, tuple[int, float, np.ndarray]] = {}
        self.latest_processed_frames: dict[str, tuple[float, np.ndarray]] = {}
        self.stream_exporter = FrameStreamExporter(project_root)
        self.live_status_path = project_root / "data" / "live_status.json"
        self._last_live_status_write_at = 0.0
        self._next_raw_emit_at: dict[str, float] = {camera_id: 0.0 for camera_id in self.config.cameras}
        self._raw_gui_interval_seconds = 1.0 / 15.0
        self.camera_devices = discover_cameras()
        self.camera_device_infos: list[CameraDeviceInfo] = []
        self.views: dict[str, CameraView] = {}
        self.count_labels: dict[str, QLabel] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.camera_selects: dict[str, QComboBox] = {}
        self._build_ui()
        self._wire_signals()
        self._repair_camera_assignments()
        self._refresh_model_status()
        self._maybe_start_setup_wizard()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_host_status)
        self._status_timer.start(1000)
        self._external_stop_file = self.project_root / "logs" / "visitor_counter.stop"
        self._external_stop_timer = QTimer(self)
        self._external_stop_timer.timeout.connect(self._poll_external_stop)
        self._external_stop_timer.start(500)
        self._camera_repair_timer = QTimer(self)
        self._camera_repair_timer.timeout.connect(self._poll_camera_assignments)
        self._camera_repair_timer.start(5000)
        self.start_processing()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.model_label = QLabel()
        self.fallback_label = QLabel()
        self.fallback_label.setStyleSheet("font-weight:bold;color:#b40000;")
        top.addWidget(self.model_label, 1)
        top.addWidget(self.fallback_label)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        for camera_id in ("camera_1", "camera_2"):
            box = QGroupBox("Kamera 1" if camera_id == "camera_1" else "Kamera 2")
            camera_layout = QVBoxLayout(box)
            view = CameraView(camera_id)
            view.set_line(self.config.cameras[camera_id].line_start, self.config.cameras[camera_id].line_end)
            self.views[camera_id] = view
            camera_layout.addWidget(view, 1)
            self.camera_selects[camera_id] = QComboBox()
            camera_layout.addWidget(self.camera_selects[camera_id])
            splitter.addWidget(box)
        layout.addWidget(splitter, 1)

        lower = QHBoxLayout()
        lower.addWidget(self._build_counts_panel(), 2)
        lower.addWidget(self._build_camera_settings_panel(), 2)
        lower.addWidget(self._build_status_panel(), 2)
        lower.addWidget(self._build_controls_panel(), 1)
        layout.addLayout(lower)
        self.setCentralWidget(root)

        fullscreen = QAction("Vollbild", self)
        fullscreen.triggered.connect(lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())
        self.menuBar().addAction(fullscreen)
        settings_menu = self.menuBar().addMenu("Einstellungen")
        wizard_action = QAction("Einrichtungsassistent starten", self)
        wizard_action.triggered.connect(self.start_setup_wizard)
        settings_menu.addAction(wizard_action)

    def _build_counts_panel(self) -> QGroupBox:
        panel = QGroupBox("Zaehlwerte")
        grid = QGridLayout(panel)
        names = [
            "global_inside",
            "global_in",
            "global_out",
            "camera_1_in",
            "camera_1_out",
            "camera_1_visible",
            "camera_2_in",
            "camera_2_out",
            "camera_2_visible",
            "suppressed",
            "uncertain",
        ]
        for index, name in enumerate(names):
            label = QLabel("0")
            label.setStyleSheet("font-size:24px;font-weight:bold;")
            self.count_labels[name] = label
            grid.addWidget(QLabel(name.replace("_", " ")), index // 3 * 2, index % 3)
            grid.addWidget(label, index // 3 * 2 + 1, index % 3)
        return panel

    def _build_status_panel(self) -> QGroupBox:
        panel = QGroupBox("Status")
        form = QFormLayout(panel)
        for name in [
            "camera_1",
            "camera_2",
            "camera_fps",
            "inference_fps",
            "render_fps",
            "backend",
            "hailo_latency",
            "total_latency",
            "latency_p95",
            "frame_age",
            "queue",
            "dropped_frames",
            "cpu",
            "ram",
            "temperature",
            "hailo",
            "hef",
            "osnet",
            "osnet_latency",
            "last_detection",
        ]:
            label = QLabel("-")
            self.status_labels[name] = label
            form.addRow(name.replace("_", " "), label)
        return panel

    def _build_camera_settings_panel(self) -> QGroupBox:
        panel = QGroupBox("Kameraeinstellungen")
        layout = QVBoxLayout(panel)
        form = QFormLayout()
        for camera_id, text in (("camera_1", "Kamera 1"), ("camera_2", "Kamera 2")):
            combo = QComboBox()
            combo.setMinimumWidth(360)
            self.camera_selects[camera_id] = combo
            form.addRow(text, combo)
        layout.addLayout(form)
        buttons = QGridLayout()
        actions = [
            ("Kameras neu suchen", self.refresh_cameras),
            ("Kamera 1 testen", lambda: self.test_camera("camera_1")),
            ("Kamera 2 testen", lambda: self.test_camera("camera_2")),
            ("Auswahl uebernehmen", self.apply_camera_selection),
            ("Kameraeinstellungen speichern", self.save_camera_settings),
            ("Modellstatus pruefen", self.check_model_status),
            ("HEF-Datei auswaehlen", self.select_hef_file),
        ]
        for index, (text, handler) in enumerate(actions):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)
        return panel

    def _build_controls_panel(self) -> QGroupBox:
        panel = QGroupBox("Bedienung")
        layout = QVBoxLayout(panel)
        for text, handler in [
            ("Start", self.start_processing),
            ("Stopp", self.stop_processing),
            ("Neustart", self.restart_processing),
            ("Zaehler zuruecksetzen", self.reset_counts),
            ("Kameras neu erkennen", self.refresh_cameras),
            ("Einstellungen speichern", self.save_settings),
            ("Diagnosebericht", self.write_diagnostics),
            ("Beenden", self.close),
        ]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            layout.addWidget(button)

        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.01, 0.99)
        self.confidence_spin.setSingleStep(0.01)
        self.confidence_spin.setValue(self.config.model.confidence_threshold)
        self.consensus_spin = QDoubleSpinBox()
        self.consensus_spin.setRange(0.1, 30.0)
        self.consensus_spin.setValue(self.config.consensus.transition_window_seconds)
        self.lost_spin = QSpinBox()
        self.lost_spin.setRange(0, 300)
        self.lost_spin.setValue(self.config.tracking.max_lost_frames)
        form = QFormLayout()
        form.addRow("Konfidenz", self.confidence_spin)
        form.addRow("Konsensfenster s", self.consensus_spin)
        form.addRow("Max lost frames", self.lost_spin)
        layout.addLayout(form)
        layout.addStretch(1)
        return panel

    def _wire_signals(self) -> None:
        self.frame_ready.connect(self._on_frame_ready)
        self.raw_frame_ready.connect(self._on_raw_frame_ready)
        self.stats_ready.connect(self._on_stats_ready)
        for view in self.views.values():
            view.line_changed.connect(self._on_line_changed)
        self.refresh_cameras()

    def start_processing(self) -> None:
        if any(capture.is_alive() for capture in self.captures) or (self.pipeline and self.pipeline.is_alive()):
            return
        self._repair_camera_assignments()
        self.stop_event = Event()
        self.frame_queue = LatestFrameHub(list(self.config.cameras))
        self.captures = [
            CameraCapture(camera_config, self.frame_queue, self.stop_event, frame_callback=self._on_capture_packet)
            for camera_config in self.config.cameras.values()
            if camera_config.device
        ]
        self.pipeline = None
        if not self.config.display.display_raw_frames_only:
            self.pipeline = ProcessingPipeline(
                self.config,
                self.project_root,
                self.frame_queue,
                self.stop_event,
                frame_callback=lambda camera_id, frame, tracks: self.frame_ready.emit(camera_id, frame, tracks),
                stats_callback=lambda stats, counts: self.stats_ready.emit(stats, counts),
            )
        for capture in self.captures:
            capture.start()
        if self.pipeline:
            self.pipeline.start()
        LOGGER.info("Display raw frames only mode: %s", self.config.display.display_raw_frames_only)

    def stop_processing(self) -> None:
        self.stop_event.set()
        for capture in self.captures:
            capture.join(timeout=2.0)
        if self.pipeline:
            self.pipeline.join(timeout=2.0)

    def restart_processing(self) -> None:
        self.stop_processing()
        self.start_processing()

    def reset_counts(self) -> None:
        if self.pipeline:
            self.pipeline.reset_counts()
        for label in self.count_labels.values():
            label.setText("0")

    def refresh_cameras(self) -> None:
        self.camera_device_infos = discover_camera_devices()
        self.camera_devices = [info.video_node for info in self.camera_device_infos]
        self._repair_camera_assignments()
        for camera_id, combo in self.camera_selects.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Nicht ausgewaehlt", None)
            if not self.camera_device_infos:
                combo.addItem("Keine Kamera erkannt", None)
            for info in self.camera_device_infos:
                combo.addItem(info.label, info.stable_path)
            current = self.config.cameras[camera_id].device
            if current:
                index = combo.findData(current)
                if index < 0:
                    index = combo.findData(self._stable_for_video_node(current))
                if index >= 0:
                    combo.setCurrentIndex(index)
                else:
                    combo.addItem(f"Gespeicherte Kamera nicht gefunden: {current}", current)
                    combo.setCurrentIndex(combo.count() - 1)
            combo.currentIndexChanged.connect(lambda _index, cid=camera_id: self._camera_selection_changed(cid))
            combo.blockSignals(False)
        if not self.camera_device_infos:
            self._show_warning("Keine Kamera erkannt.")

    def _repair_camera_assignments(self, save: bool = True) -> bool:
        if not self.camera_device_infos:
            self.camera_device_infos = discover_camera_devices()
        stable_paths = [info.stable_path for info in self.camera_device_infos]
        available = set(stable_paths)
        used: set[str] = set()
        changed = False

        for camera_id in sorted(self.config.cameras):
            camera = self.config.cameras[camera_id]
            current = self._stable_for_any_device(camera.device)
            if current and current in available and current not in used:
                if camera.device != current:
                    camera.device = current
                    changed = True
                used.add(current)
                continue
            if camera.device is not None:
                LOGGER.warning("Clearing unavailable camera path for %s: %s", camera_id, camera.device)
                camera.device = None
                changed = True

        for camera_id in sorted(self.config.cameras):
            camera = self.config.cameras[camera_id]
            if camera.device:
                continue
            replacement = next((path for path in stable_paths if path not in used), None)
            if replacement is None:
                continue
            LOGGER.info("Assigning discovered camera to %s: %s", camera_id, replacement)
            camera.device = replacement
            used.add(replacement)
            changed = True

        if changed and save:
            save_config(self.config, self.config_path)
        return changed

    def _poll_camera_assignments(self) -> None:
        if all(camera.device for camera in self.config.cameras.values()):
            return
        self.camera_device_infos = discover_camera_devices()
        if not self._repair_camera_assignments():
            return
        self.refresh_cameras()
        if self.captures or self.pipeline:
            self.restart_processing()

    def save_settings(self) -> None:
        self._persist_settings()
        QMessageBox.information(self, "Gespeichert", f"Einstellungen gespeichert: {self.config_path}")

    def _persist_settings(self) -> None:
        self.config.model.confidence_threshold = float(self.confidence_spin.value())
        self.config.consensus.transition_window_seconds = float(self.consensus_spin.value())
        self.config.tracking.max_lost_frames = int(self.lost_spin.value())
        save_config(self.config, self.config_path)

    def write_diagnostics(self) -> None:
        report = collect_diagnostics(self.project_root)
        QMessageBox.information(self, "Diagnosebericht", f"Diagnose gespeichert. Kameras: {len(report['cameras'])}")

    def apply_camera_selection(self) -> None:
        first = self.camera_selects["camera_1"].currentData()
        second = self.camera_selects["camera_2"].currentData()
        if first and second and first == second:
            self._show_warning("Kamera wird bereits als Kamera 1 verwendet.")
            return
        was_running = self.pipeline is not None and self.pipeline.is_alive()
        if was_running:
            self.stop_processing()
        for camera_id in ("camera_1", "camera_2"):
            stable_path = self.camera_selects[camera_id].currentData()
            self.config.cameras[camera_id].device = stable_path if stable_path else None
        if was_running:
            self.start_processing()

    def save_camera_settings(self) -> None:
        self.apply_camera_selection()
        save_config(self.config, self.config_path)
        QMessageBox.information(self, "Gespeichert", "Kameraeinstellungen gespeichert.")

    def test_camera(self, camera_id: str) -> None:
        stable_path = self.camera_selects[camera_id].currentData()
        device = self._video_node_for_stable_path(stable_path) if stable_path else self.config.cameras[camera_id].device
        if not device:
            self._show_warning("Keine Kamera ausgewaehlt.")
            return
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        try:
            if not cap.isOpened():
                self._show_warning("Kamera konnte nicht geoeffnet werden.")
                return
            ok, frame = cap.read()
            if not ok or frame is None:
                self._show_warning("Kamera konnte kein Bild liefern.")
                return
            self.views[camera_id].set_frame(frame)
            QMessageBox.information(self, "Kameratest", f"{camera_id} liefert ein Bild von {device}.")
        finally:
            cap.release()

    def check_model_status(self) -> None:
        status = self._model_status_lines()
        self._refresh_model_status()
        QMessageBox.information(self, "Modellstatus", "\n".join(status))

    def select_hef_file(self) -> None:
        selected = choose_hef_file(self)
        if not selected:
            return
        source = Path(selected)
        target = self.project_root / self.config.model.custom_target_hef_path
        valid, message = self._validate_hef_basic(source)
        if not valid:
            self._show_warning(message)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        self.config.model.hef_path = str(target.relative_to(self.project_root))
        save_config(self.config, self.config_path)
        self._refresh_model_status()
        QMessageBox.information(self, "HEF-Datei", f"HEF kopiert nach {target}")

    def start_setup_wizard(self) -> None:
        SetupWizard(self).exec()
        self.refresh_cameras()
        self._refresh_model_status()

    def _maybe_start_setup_wizard(self) -> None:
        marker = self.project_root / "config" / ".setup_complete"
        if marker.exists():
            return
        QTimer.singleShot(500, self.start_setup_wizard)

    def _complete_setup(self) -> None:
        marker = self.project_root / "config" / ".setup_complete"
        marker.write_text("ok\n", encoding="utf-8")

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self.stop_processing()
        self.stream_exporter.close()
        self._persist_settings()
        event.accept()

    def _poll_external_stop(self) -> None:
        if self._external_stop_file.exists():
            QApplication.closeAllWindows()
            QApplication.quit()

    def _camera_selection_changed(self, camera_id: str) -> None:
        _ = camera_id

    def _on_line_changed(self, camera_id: str, start: tuple[int, int], end: tuple[int, int]) -> None:
        self.config.cameras[camera_id].line_start = start
        self.config.cameras[camera_id].line_end = end

    def _on_capture_packet(self, packet: FramePacket) -> None:
        now = monotonic()
        if now < self._next_raw_emit_at.get(packet.camera_id, 0.0):
            return
        self._next_raw_emit_at[packet.camera_id] = now + self._raw_gui_interval_seconds
        frame = packet.image.copy()
        if self.config.display.raw_frame_overlay:
            self._draw_raw_overlay(packet, frame)
        self.raw_frame_ready.emit(packet.camera_id, frame, packet.frame_id, packet.captured_at)

    def _draw_raw_overlay(self, packet: FramePacket, frame: np.ndarray) -> None:
        label = "CAMERA 1 RAW" if packet.camera_id == "camera_1" else "CAMERA 2 RAW"
        lines = [
            label,
            f"frame_id: {packet.frame_id}",
            f"timestamp: {packet.captured_at:.3f}",
            f"resolution: {packet.width}x{packet.height}",
        ]
        cv2.rectangle(frame, (0, 0), (360, 118), (0, 0, 0), -1)
        for index, line in enumerate(lines):
            cv2.putText(
                frame,
                line,
                (16, 28 + index * 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                (0, 255, 120),
                2,
                cv2.LINE_AA,
            )

    def _on_raw_frame_ready(self, camera_id: str, frame: object, frame_id: int, captured_at: float) -> None:
        if not isinstance(frame, np.ndarray):
            return
        age_ms = (time() - captured_at) * 1000.0
        self.latest_raw_frames[camera_id] = (frame_id, captured_at, frame)
        if frame_id % 30 == 0:
            LOGGER.info("GUI_RECEIVE camera=%s frame=%s age_ms=%.1f", camera_id, frame_id, age_ms)
        if time() - self.latest_processed_frames.get(camera_id, (0.0, frame))[0] > 0.75:
            self.stream_exporter.submit(camera_id, frame, frame_id, "raw")
        self._render_frame(camera_id, frame, frame_id, "raw")

    def _on_frame_ready(self, camera_id: str, frame: object, tracks: list[TrackedObject]) -> None:
        _ = tracks
        if isinstance(frame, np.ndarray):
            self.latest_processed_frames[camera_id] = (time(), frame)
            fallback_frame_id = self.latest_raw_frames.get(camera_id, (-1, 0.0, frame))[0]
            self.stream_exporter.submit(camera_id, frame, fallback_frame_id, "processed")
            self._render_frame(camera_id, frame, fallback_frame_id, "processed")

    def _render_frame(self, camera_id: str, frame: np.ndarray, frame_id: int, source: str) -> None:
        try:
            self.views[camera_id].set_frame(frame)
        except (KeyError, ValueError, cv2.error) as exc:
            LOGGER.error("GUI_RENDER_FAILED camera=%s frame=%s source=%s error=%s", camera_id, frame_id, source, exc)
            return
        
        # Calculate Render FPS
        now = time()
        if not hasattr(self, "_render_frames"):
            self._render_frames = 0
            self._last_render_time = now
        self._render_frames += 1
        if now - self._last_render_time >= 1.0:
            render_fps = self._render_frames / (now - self._last_render_time)
            self.status_labels["render_fps"].setText(f"{render_fps:.1f}")
            self._render_frames = 0
            self._last_render_time = now

        if frame_id >= 0 and frame_id % 30 == 0:
            LOGGER.info("GUI_RENDER camera=%s frame=%s source=%s timestamp=%.3f", camera_id, frame_id, source, time())

    def _on_stats_ready(self, stats: RuntimeStats, counts: GlobalCounts) -> None:
        self.count_labels["global_inside"].setText(str(counts.inside))
        self.count_labels["global_in"].setText(str(counts.entered))
        self.count_labels["global_out"].setText(str(counts.exited))
        self.count_labels["suppressed"].setText(str(counts.suppressed_duplicates))
        self.count_labels["uncertain"].setText(str(counts.uncertain_consensus))
        if self.pipeline:
            for camera_id, counter in self.pipeline.counters.items():
                self.count_labels[f"{camera_id}_in"].setText(str(counter.counts.entered))
                self.count_labels[f"{camera_id}_out"].setText(str(counter.counts.exited))
                self.count_labels[f"{camera_id}_visible"].setText(str(counter.counts.visible))
        self.status_labels["inference_fps"].setText(f"{stats.inference_fps:.1f}")
        self.status_labels["backend"].setText(stats.backend or "-")
        self.status_labels["hailo_latency"].setText(f"{stats.inference_latency_ms:.1f} ms")
        self.status_labels["total_latency"].setText(f"{stats.total_latency_ms:.1f} ms")
        p95 = stats.latency.get("end_to_end_ms")
        self.status_labels["latency_p95"].setText("-" if p95 is None else f"{p95.p95_ms:.1f} ms")
        self.status_labels["frame_age"].setText(f"{stats.frame_age_ms:.1f} ms")
        self.status_labels["queue"].setText(f"{stats.queue_length}/{max(1, len(self.config.cameras))}")
        self.status_labels["dropped_frames"].setText(
            " / ".join(f"{camera_id}: {count}" for camera_id, count in sorted(stats.dropped_frames.items())) or "0"
        )
        self.status_labels["hailo"].setText(
            f"{stats.hailo_status} | {stats.hailo_device} | calls={stats.hailo_inference_count}"
        )
        if stats.active_hef_sha256:
            self.status_labels["hef"].setText(f"{stats.active_hef} ({stats.active_hef_sha256[:12]})")
        if stats.reid_status:
            suffix = f" ({stats.reid_hef_sha256[:12]})" if stats.reid_hef_sha256 else ""
            self.status_labels["osnet"].setText(
                f"{stats.reid_status}{suffix} | calls={stats.reid_inference_count} cache={stats.reid_cache_size}"
            )
        self.status_labels["osnet_latency"].setText(f"{stats.reid_latency_ms:.1f} ms")
        self.status_labels["last_detection"].setText("-" if stats.last_detection_at is None else f"{time():.0f}")
        self._write_live_status(stats, counts)

    def _write_live_status(self, stats: RuntimeStats, counts: GlobalCounts) -> None:
        now = time()
        if now - self._last_live_status_write_at < 1.0:
            return
        self._last_live_status_write_at = now

        cameras = []
        captures = {capture.config.camera_id: capture for capture in self.captures}
        for camera_id, camera_config in self.config.cameras.items():
            capture = captures.get(camera_id)
            counter = self.pipeline.counters.get(camera_id) if self.pipeline else None
            frame_info = self.latest_raw_frames.get(camera_id)
            last_frame_time = frame_info[1] if frame_info else None
            camera_stats = capture.stats if capture else None
            connected = bool(camera_stats.connected) if camera_stats else False
            cameras.append(
                {
                    "camera_id": camera_id,
                    "name": camera_config.display_name,
                    "role": camera_config.role,
                    "source": "USB" if camera_config.device else None,
                    "device": camera_config.device,
                    "wanted_fps": camera_config.fps,
                    "width": camera_config.width,
                    "height": camera_config.height,
                    "status": "ONLINE" if connected else "OFFLINE",
                    "actual_fps": round(camera_stats.fps, 1) if camera_stats else None,
                    "last_frame_time": last_frame_time,
                    "seconds_since_last_frame": round(now - last_frame_time, 3) if last_frame_time else None,
                    "connected_seconds": None,
                    "reconnect_count": None,
                    "dropped_frames": camera_stats.dropped_frames if camera_stats else None,
                    "decode_errors": None,
                    "last_error": "" if connected else (camera_stats.last_error if camera_stats else "not started"),
                    "visible": counter.counts.visible if counter else 0,
                    "entered": counter.counts.entered if counter else 0,
                    "exited": counter.counts.exited if counter else 0,
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
                "last_event_time": stats.last_detection_at,
            },
            "cameras": cameras,
            "runtime": {
                "inference_fps": round(stats.inference_fps, 1),
                "hailo_latency_ms": round(stats.inference_latency_ms, 1),
                "total_latency_ms": round(stats.total_latency_ms, 1),
                "frame_age_ms": round(stats.frame_age_ms, 1),
                "hailo_status": stats.hailo_status,
                "hailo_device": stats.hailo_device,
                "hailo_inference_count": stats.hailo_inference_count,
                "active_hef": stats.active_hef,
                "queue_length": stats.queue_length,
            },
        }
        try:
            self.live_status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.live_status_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            tmp_path.replace(self.live_status_path)
        except OSError as exc:
            LOGGER.warning("LIVE_STATUS_WRITE_FAILED path=%s error=%s", self.live_status_path, exc)

    def _poll_host_status(self) -> None:
        import os
        self.status_labels["cpu"].setText(f"{psutil.cpu_percent(interval=None):.0f}%")
        
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        try:
            proc = psutil.Process(os.getpid())
            rss_mb = proc.memory_info().rss / 1024 / 1024
            vms_mb = proc.memory_info().vms / 1024 / 1024
        except Exception:
            rss_mb, vms_mb = 0.0, 0.0
            
        ram_text = (
            f"T:{vm.total/1024/1024:.0f}MB | U:{vm.used/1024/1024:.0f}MB | "
            f"F:{vm.free/1024/1024:.0f}MB | S:{swap.used/1024/1024:.0f}MB | "
            f"RSS:{rss_mb:.0f}MB | VMS:{vms_mb:.0f}MB"
        )
        self.status_labels["ram"].setText(ram_text)
        
        temp = read_pi_temperature_c()
        self.status_labels["temperature"].setText("-" if temp is None else f"{temp:.1f} C")
        if self.captures:
            self.status_labels["camera_fps"].setText(
                " / ".join(f"{capture.config.camera_id}: {capture.stats.fps:.1f}" for capture in self.captures)
            )
            for capture in self.captures:
                self.status_labels[capture.config.camera_id].setText("verbunden" if capture.stats.connected else capture.stats.last_error)

    def _refresh_model_status(self) -> None:
        status = ModelManager(self.config.model, self.project_root).status()
        self.model_label.setText(f"Zielmodell: {status.target_name} | Aktiver Detektor: {status.active_display_name}")
        lines = self._model_status_lines()
        self.fallback_label.setText(" | ".join(lines[:3]))
        self.status_labels["hef"].setText(str(status.path))

    def _model_status_lines(self) -> list[str]:
        pt = self.project_root / "models" / "yolo26m_640.onnx"
        onnx_postprocess = ModelManager(self.config.model, self.project_root).postprocess_onnx_path
        status = ModelManager(self.config.model, self.project_root).status()
        hef = status.path
        lines = [
            "YOLO26m ONNX vorhanden" if pt.exists() else "YOLO26m ONNX fehlt",
            "YOLO26m Postprocess vorhanden" if onnx_postprocess and onnx_postprocess.exists() else "YOLO26m Postprocess fehlt",
        ]
        if not status.exists:
            lines.append("YOLO26m Detection HEF fehlt")
            lines.append("YOLO26m Detection ist noch nicht fuer Hailo-10H installiert. Personenerkennung und Zaehlung sind deaktiviert.")
        else:
            valid, message = self._validate_hef_basic(hef)
            lines.append("YOLO26m Detection HEF lesbar" if valid else f"YOLO26m HEF ungueltig: {message}")
        reid_status = OSNetReIDManager(self.config.model, self.project_root).status(validate_hailo=False)
        lines.append(reid_status.message)
        try:
            hailo = subprocess.run(["hailortcli", "scan"], capture_output=True, text=True, timeout=5)
            lines.append("Hailo-10H erkannt" if "Device:" in hailo.stdout else "Hailo-10H nicht erkannt")
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            lines.append(f"Hailo-10H Status nicht pruefbar: {exc}")
        return lines

    def _validate_hef_basic(self, path: Path) -> tuple[bool, str]:
        try:
            import hailo_platform

            hef = hailo_platform.HEF(str(path))
            inputs = hef.get_input_vstream_infos()
            outputs = hef.get_output_vstream_infos()
            if not inputs or not outputs:
                return False, "HEF enthaelt keine erkennbaren Ein- oder Ausgangstensoren."
            names = " ".join(info.name for info in inputs + outputs)
            return True, f"HEF lesbar. Tensoren: {names}"
        except Exception as exc:  # noqa: BLE001
            return False, f"HailoRT konnte die HEF nicht lesen: {exc}"

    def _video_node_for_stable_path(self, stable_path: str | None) -> str | None:
        if not stable_path:
            return None
        for info in self.camera_device_infos:
            if stable_path in {info.stable_path, info.video_node}:
                return info.video_node
        path = Path(stable_path)
        if path.exists():
            return str(path.resolve())
        return stable_path

    def _stable_for_video_node(self, video_node: str) -> str | None:
        for info in self.camera_device_infos:
            if info.video_node == video_node:
                return info.stable_path
        return None

    def _stable_for_any_device(self, device: str | None) -> str | None:
        if not device:
            return None
        for info in self.camera_device_infos:
            if device in {info.stable_path, info.video_node}:
                return info.stable_path
            try:
                if Path(device).resolve() == Path(info.video_node).resolve():
                    return info.stable_path
            except OSError:
                pass
        return device if Path(device).exists() else None

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Personenzaehler", message)


class SetupWizard(QDialog):
    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Einrichtungsassistent")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.preview_1 = CameraView("camera_1")
        self.preview_2 = CameraView("camera_2")
        previews = QHBoxLayout()
        previews.addWidget(self.preview_1)
        previews.addWidget(self.preview_2)
        layout.addLayout(previews, 1)
        buttons = QHBoxLayout()
        for text, handler in [
            ("Pruefen", self.refresh_summary),
            ("Testbilder anzeigen", self.show_test_images),
            ("Konfiguration speichern", self.save_and_close),
            ("Ueberspringen", self.reject),
        ]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.refresh_summary()

    def refresh_summary(self) -> None:
        self.main_window.refresh_cameras()
        lines = self.main_window._model_status_lines()
        devices = self.main_window.camera_device_infos
        lines.append(f"Verfuegbare Kameras: {len(devices)}")
        for index, info in enumerate(devices, start=1):
            lines.append(f"{index}. {info.label}")
        self.summary.setText("\n".join(lines))

    def show_test_images(self) -> None:
        for camera_id, preview in (("camera_1", self.preview_1), ("camera_2", self.preview_2)):
            stable = self.main_window.camera_selects[camera_id].currentData()
            device = self.main_window._video_node_for_stable_path(stable)
            if not device:
                continue
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            try:
                ok, frame = cap.read()
                if ok and frame is not None:
                    preview.set_frame(frame)
            finally:
                cap.release()

    def save_and_close(self) -> None:
        self.main_window.save_camera_settings()
        self.main_window._complete_setup()
        self.accept()


def run_gui(project_root: Path) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(project_root)
    stop_file = project_root / "logs" / "visitor_counter.stop"
    stop_file.unlink(missing_ok=True)
    read_socket, write_socket = socket.socketpair()
    read_socket.setblocking(False)
    write_socket.setblocking(False)
    signal.set_wakeup_fd(write_socket.fileno())

    def request_shutdown(_signum: int, _frame: object) -> None:
        pass

    def drain_signal_socket() -> None:
        try:
            read_socket.recv(1024)
        except BlockingIOError:
            pass
        window.close()
        app.quit()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    signal_notifier = QSocketNotifier(read_socket.fileno(), QSocketNotifier.Read)
    signal_notifier.activated.connect(drain_signal_socket)
    signal_timer = QTimer(window)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(250)
    window._signal_resources = (read_socket, write_socket, signal_notifier, signal_timer)  # type: ignore[attr-defined]
    app.aboutToQuit.connect(signal_timer.stop)
    app.aboutToQuit.connect(window._camera_repair_timer.stop)
    app.aboutToQuit.connect(lambda: stop_file.unlink(missing_ok=True))
    app.aboutToQuit.connect(signal_notifier.setEnabled(False))
    app.aboutToQuit.connect(lambda: signal.set_wakeup_fd(-1))
    app.aboutToQuit.connect(read_socket.close)
    app.aboutToQuit.connect(write_socket.close)
    window.show()
    while window.isVisible():
        app.processEvents()
        if stop_file.exists():
            window.close()
            break
        sleep(0.05)
    app.quit()
    app.processEvents()
    stop_file.unlink(missing_ok=True)
    return 0


def choose_hef_file(parent: QWidget) -> str | None:
    path, _ = QFileDialog.getOpenFileName(parent, "HEF-Datei auswaehlen", "models", "Hailo HEF (*.hef)")
    return path or None
