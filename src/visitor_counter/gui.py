from __future__ import annotations

from pathlib import Path
import signal
import socket
import shutil
import subprocess
from threading import Event
from time import sleep, time
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
from .types import RuntimeStats, TrackedObject


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
    stats_ready = Signal(object, object)

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = project_root
        self.config_path = project_root / "config" / "config.yaml"
        self.config = load_config(self.config_path)
        configure_logging(project_root / "logs")
        self.setWindowTitle("YOLO26x Dual-Kamera Besucherzaehler")
        self.resize(1500, 900)
        self.frame_queue = LatestFrameHub(list(self.config.cameras))
        self.stop_event = Event()
        self.captures: list[CameraCapture] = []
        self.pipeline: ProcessingPipeline | None = None
        self.camera_devices = discover_cameras()
        self.camera_device_infos: list[CameraDeviceInfo] = []
        self.views: dict[str, CameraView] = {}
        self.count_labels: dict[str, QLabel] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.camera_selects: dict[str, QComboBox] = {}
        self._build_ui()
        self._wire_signals()
        self._refresh_model_status()
        self._maybe_start_setup_wizard()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_host_status)
        self._status_timer.start(1000)
        self._external_stop_file = self.project_root / "logs" / "visitor_counter.stop"
        self._external_stop_timer = QTimer(self)
        self._external_stop_timer.timeout.connect(self._poll_external_stop)
        self._external_stop_timer.start(500)

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
        self.stats_ready.connect(self._on_stats_ready)
        for view in self.views.values():
            view.line_changed.connect(self._on_line_changed)
        self.refresh_cameras()

    def start_processing(self) -> None:
        if self.pipeline and self.pipeline.is_alive():
            return
        self.stop_event = Event()
        self.frame_queue = LatestFrameHub(list(self.config.cameras))
        self.captures = [
            CameraCapture(camera_config, self.frame_queue, self.stop_event)
            for camera_config in self.config.cameras.values()
        ]
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
        self.pipeline.start()

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
        target = self.project_root / "models" / "yolo26x_person_hailo10h_640.hef"
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

    def _on_frame_ready(self, camera_id: str, frame: object, tracks: list[TrackedObject]) -> None:
        _ = tracks
        if isinstance(frame, np.ndarray):
            self.views[camera_id].set_frame(frame)

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

    def _poll_host_status(self) -> None:
        self.status_labels["cpu"].setText(f"{psutil.cpu_percent(interval=None):.0f}%")
        self.status_labels["ram"].setText(f"{psutil.virtual_memory().percent:.0f}%")
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
        pt = self.project_root / "models" / "yolo26x.pt"
        onnx = self.project_root / "models" / "yolo26x_640.onnx"
        status = ModelManager(self.config.model, self.project_root).status()
        hef = status.path
        lines = [
            "YOLO26x PT vorhanden" if pt.exists() else "YOLO26x PT fehlt",
            "YOLO26x ONNX vorhanden" if onnx.exists() else "YOLO26x ONNX fehlt",
        ]
        if not status.exists:
            lines.append("YOLO26x HEF fehlt")
            lines.append("YOLO26x ist noch nicht fuer Hailo-10H kompiliert. Personenerkennung und Zaehlung sind deaktiviert.")
        else:
            valid, message = self._validate_hef_basic(hef)
            lines.append("Custom YOLO26x HEF lesbar" if valid else f"YOLO26x HEF ungueltig: {message}")
        reid_status = OSNetReIDManager(self.config.model, self.project_root).status(validate_hailo=False)
        lines.append(reid_status.message)
        hailo = subprocess.run(["hailortcli", "scan"], capture_output=True, text=True, timeout=5)
        lines.append("Hailo-10H erkannt" if "Device:" in hailo.stdout else "Hailo-10H nicht erkannt")
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
