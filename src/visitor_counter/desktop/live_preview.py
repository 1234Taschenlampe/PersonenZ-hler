"""Low-rate, in-memory desktop previews for cameras already online in the counter.

The desktop UI runs in a different process from the counting service. Preview
connections therefore use their own bounded RTSP reader; they never alter the
capture/AI pipeline, write images to disk or expose credentials in UI labels.
"""
from __future__ import annotations

from threading import Event
from time import monotonic
from typing import Any

import cv2
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..camera_manager import open_camera_source
from ..privacy import anonymize_frame
from .components import Card


def online_camera_sources(
    cameras: list[dict[str, Any]], sources: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Select healthy, configured streams independently of every other camera."""
    active: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for camera in cameras:
        camera_id = str(camera.get("camera_id", ""))
        source = sources.get(camera_id, "")
        if not camera_id or not source or camera_id in seen:
            continue
        if str(camera.get("status", "")).upper() != "ONLINE":
            continue
        try:
            fps = float(camera.get("actual_fps") or 0)
            age = camera.get("seconds_since_last_frame")
            if fps <= 0 or (age is not None and float(age) > 8.0):
                continue
        except (TypeError, ValueError):
            continue
        seen.add(camera_id)
        active.append((camera_id, str(camera.get("name") or camera_id), source))
    return active


class _PreviewReader(QThread):
    image_ready = Signal(str, QImage)
    failed = Signal(str, str)

    def __init__(
        self, camera_id: str, source: str, parent: QWidget, *, pixel_size: int = 24
    ) -> None:
        super().__init__(parent)
        self.camera_id = camera_id
        self.source = source
        self.pixel_size = max(24, pixel_size)
        self._stop_requested = Event()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        capture = None
        try:
            capture = open_camera_source(self.source, timeout_ms=3500)
            if not capture.isOpened():
                self.failed.emit(self.camera_id, "Vorschau nicht erreichbar")
                return
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            next_frame_at = 0.0
            while not self._stop_requested.is_set():
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    self.failed.emit(self.camera_id, "Vorschau unterbrochen")
                    break
                now = monotonic()
                if now < next_frame_at:
                    continue
                height, width = frame.shape[:2]
                if width <= 0 or height <= 0:
                    continue
                target_width = min(width, 800)
                target_height = max(1, round(height * target_width / width))
                if target_width != width:
                    frame = cv2.resize(
                        frame, (target_width, target_height), interpolation=cv2.INTER_AREA
                    )
                # Never deliver identifiable raw frames to the desktop.
                # No tracked boxes are available in the independent preview reader,
                # so person-only anonymization would be ineffective here.
                frame = anonymize_frame(
                    frame, mode="full_frame", pixel_size=self.pixel_size
                )
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = QImage(
                    rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0],
                    QImage.Format_RGB888,
                ).copy()
                self.image_ready.emit(self.camera_id, image)
                next_frame_at = now + 0.7  # previews must not saturate the GUI
        except (OSError, TypeError, ValueError, cv2.error):
            self.failed.emit(self.camera_id, "Vorschau nicht verfügbar")
        finally:
            if capture is not None:
                capture.release()


class _ClickableImage(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _PreviewTile(Card):
    def __init__(self, camera_id: str, name: str, on_expand: Any) -> None:
        super().__init__()
        self.camera_id = camera_id
        self.name = name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        title = QLabel(name)
        title.setStyleSheet("font-weight:600;")
        live = QLabel("LIVE")
        live.setProperty("muted", True)
        enlarge = QPushButton("Vergrößern")
        enlarge.clicked.connect(on_expand)
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(live)
        heading.addWidget(enlarge)
        layout.addLayout(heading)
        self.image = _ClickableImage("Livebild wird geladen …")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumHeight(180)
        self.image.setMaximumHeight(225)
        self.image.setStyleSheet(
            "background:#16191d;color:#e9eef4;border-radius:8px;"
        )
        self.image.setCursor(Qt.PointingHandCursor)
        self.image.clicked.connect(on_expand)
        layout.addWidget(self.image)

    def show_image(self, frame: QImage) -> None:
        self.image.setPixmap(
            QPixmap.fromImage(frame).scaled(
                max(1, self.image.width()), max(1, self.image.height()),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        )

    def clear_image(self, message: str = "Livebild wird geladen …") -> None:
        self.image.clear()
        self.image.setText(message)


class CameraPreviewPanel(QWidget):
    """Show only online feeds; manage reader lifetimes with page visibility."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        self.heading = QLabel("Live-Kameras")
        self.heading.setStyleSheet("font-size:18px;font-weight:600;")
        outer.addWidget(self.heading)
        self.summary = QLabel("Kamerastatus wird geladen …")
        self.summary.setProperty("muted", True)
        outer.addWidget(self.summary)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        outer.addLayout(self.grid)
        self._active = True
        self._preview_enabled = False  # Explicit opt-in in Datenschutz.
        self._pixel_size = 24
        self._readers: dict[str, _PreviewReader] = {}
        self._retiring: set[_PreviewReader] = set()
        self._tiles: dict[str, _PreviewTile] = {}
        self._last_images: dict[str, QImage] = {}
        self._retry_after: dict[str, float] = {}
        self._latest_cameras: list[dict[str, Any]] = []
        self._latest_sources: dict[str, str] = {}
        self._dialog: QDialog | None = None
        self._dialog_camera: str | None = None
        self._dialog_label: QLabel | None = None

    def set_preview_policy(self, *, enabled: bool, pixel_size: int = 24) -> None:
        """Apply local privacy consent immediately without restarting the Pi."""
        pixel_size = max(24, int(pixel_size))
        if self._preview_enabled == enabled and self._pixel_size == pixel_size:
            return
        self._preview_enabled = enabled
        self._pixel_size = pixel_size
        self._stop_all()
        self._last_images.clear()
        for tile in self._tiles.values():
            tile.clear_image()
        self.update_cameras(self._latest_cameras, self._latest_sources)

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        if not active:
            self._stop_all()
            self._last_images.clear()
            if self._dialog is not None:
                self._dialog.close()
            for tile in self._tiles.values():
                tile.clear_image()
        else:
            self.update_cameras(self._latest_cameras, self._latest_sources)

    def update_cameras(
        self, cameras: list[dict[str, Any]], sources: dict[str, str]
    ) -> None:
        self._latest_cameras = list(cameras)
        self._latest_sources = dict(sources)
        desired = (
            online_camera_sources(cameras, sources)
            if self._active and self._preview_enabled else []
        )
        target = {camera_id: (name, source) for camera_id, name, source in desired}
        if not self._preview_enabled:
            self.summary.setText(
                "Lokale Vorschau aus. Unter Datenschutz aktivieren; "
                "Bilder werden vollständig verpixelt."
            )
        else:
            self.summary.setText(
                f"{len(desired)} von {len(cameras)} Kameras mit Live-Vorschau"
                if desired else f"Keine Live-Kamera online (0 von {len(cameras)})"
            )
        if self._dialog is not None and self._dialog_camera not in target:
            self._dialog.close()
        for camera_id in list(self._readers):
            if camera_id not in target or self._readers[camera_id].source != target[camera_id][1]:
                self._stop_reader(camera_id)
                self._retry_after.pop(camera_id, None)
        for camera_id in list(self._tiles):
            if camera_id not in target or self._tiles[camera_id].name != target[camera_id][0]:
                tile = self._tiles.pop(camera_id)
                self.grid.removeWidget(tile)
                tile.setParent(None)
                tile.deleteLater()
                self._last_images.pop(camera_id, None)
        for index, (camera_id, name, source) in enumerate(desired):
            if camera_id not in self._tiles:
                self._tiles[camera_id] = _PreviewTile(
                    camera_id, name, lambda _checked=False, cid=camera_id: self._expand(cid)
                )
            self.grid.addWidget(self._tiles[camera_id], index // 2, index % 2)
            reader = self._readers.get(camera_id)
            if reader is None or not reader.isRunning():
                # Avoid opening a broken RTSP stream every 3-second UI refresh.
                if monotonic() < self._retry_after.get(camera_id, 0.0):
                    continue
                if reader is not None:
                    self._stop_reader(camera_id)
                reader = _PreviewReader(
                    camera_id, source, self, pixel_size=self._pixel_size
                )
                reader.image_ready.connect(
                    lambda cid, image, r=reader: (
                        self._on_image(cid, image) if self._readers.get(cid) is r else None
                    )
                )
                reader.failed.connect(
                    lambda cid, message, r=reader: (
                        self._on_failure(cid, message) if self._readers.get(cid) is r else None
                    )
                )
                self._readers[camera_id] = reader
                self._tiles[camera_id].clear_image()
                reader.start()
        if not desired and self._dialog is not None:
            self._dialog.close()

    def _on_image(self, camera_id: str, image: QImage) -> None:
        if not self._active or camera_id not in self._readers:
            return
        self._retry_after.pop(camera_id, None)
        self._last_images[camera_id] = image
        tile = self._tiles.get(camera_id)
        if tile is not None:
            tile.show_image(image)
        if self._dialog_camera == camera_id:
            self._show_dialog_image(image)

    def _on_failure(self, camera_id: str, message: str) -> None:
        self._retry_after[camera_id] = monotonic() + 8.0
        tile = self._tiles.get(camera_id)
        if tile is not None:
            tile.clear_image(message)
        self._last_images.pop(camera_id, None)
        if self._dialog_camera == camera_id and self._dialog_label is not None:
            self._dialog_label.clear()
            self._dialog_label.setText(message)

    def _expand(self, camera_id: str) -> None:
        tile = self._tiles.get(camera_id)
        if tile is None:
            return
        if self._dialog is not None:
            self._dialog.close()
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{tile.name} – Livebild")
        dialog.resize(1020, 700)
        layout = QVBoxLayout(dialog)
        label = QLabel("Livebild wird geladen …")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(600, 360)
        label.setStyleSheet("background:#16191d;color:white;")
        layout.addWidget(label)
        self._dialog = dialog
        self._dialog_camera = camera_id
        self._dialog_label = label
        dialog.finished.connect(lambda _code, d=dialog: self._clear_dialog(d))
        if camera_id in self._last_images:
            self._show_dialog_image(self._last_images[camera_id])
        dialog.open()

    def _show_dialog_image(self, image: QImage) -> None:
        label = self._dialog_label
        if label is not None:
            label.setPixmap(
                QPixmap.fromImage(image).scaled(
                    max(1, label.width()), max(1, label.height()),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
            )

    def _clear_dialog(self, dialog: QDialog) -> None:
        if self._dialog is dialog:
            self._dialog = None
            self._dialog_camera = None
            self._dialog_label = None
        dialog.deleteLater()

    def _stop_reader(self, camera_id: str) -> None:
        reader = self._readers.pop(camera_id, None)
        if reader is None:
            return
        reader.stop()
        if reader.isFinished():
            reader.deleteLater()
            return
        self._retiring.add(reader)
        reader.finished.connect(lambda r=reader: self._retiring.discard(r))
        reader.finished.connect(reader.deleteLater)

    def _stop_all(self) -> None:
        for camera_id in list(self._readers):
            self._stop_reader(camera_id)

    def shutdown(self) -> None:
        self.set_active(False)
        for reader in list(self._retiring):
            reader.wait(6500)
