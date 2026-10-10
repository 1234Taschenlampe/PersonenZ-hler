from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import subprocess
from threading import Condition, Event, Thread
from time import monotonic, time
from typing import Callable
from urllib.parse import urlparse

import cv2

from .configuration import CameraConfig
from .types import CameraStats, FramePacket

LOGGER = logging.getLogger(__name__)
FramePacketCallback = Callable[[FramePacket], None]


class LatestFrameHub:
    """Thread-safe one-slot-per-camera buffer for low-latency capture."""

    def __init__(self, camera_ids: list[str]) -> None:
        self._condition = Condition()
        self._slots: dict[str, FramePacket | None] = {camera_id: None for camera_id in camera_ids}
        self._dropped: dict[str, int] = {camera_id: 0 for camera_id in camera_ids}

    @property
    def maxsize(self) -> int:
        return max(1, len(self._slots))

    def put(self, packet: FramePacket) -> bool:
        with self._condition:
            if packet.camera_id not in self._slots:
                self._slots[packet.camera_id] = None
                self._dropped[packet.camera_id] = 0
            replaced = self._slots[packet.camera_id] is not None
            if replaced:
                self._dropped[packet.camera_id] += 1
            self._slots[packet.camera_id] = packet
            self._condition.notify()
            return replaced

    def get_next(self, camera_order: list[str], last_camera_id: str | None = None, timeout: float = 0.2, max_age_seconds: float | None = None) -> FramePacket | None:
        deadline = monotonic() + timeout
        with self._condition:
            while True:
                packet = self._take_ready(camera_order, last_camera_id, max_age_seconds)
                if packet is not None:
                    return packet
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def qsize(self) -> int:
        with self._condition:
            return sum(packet is not None for packet in self._slots.values())

    def dropped_counts(self) -> dict[str, int]:
        with self._condition:
            return dict(self._dropped)

    def _take_ready(self, camera_order: list[str], last_camera_id: str | None, max_age_seconds: float | None) -> FramePacket | None:
        ordered = self._rotated_order(camera_order, last_camera_id)
        now = monotonic()
        for camera_id in ordered:
            packet = self._slots.get(camera_id)
            if packet is None:
                continue
            if max_age_seconds is not None and now - packet.monotonic_time > max_age_seconds:
                self._slots[camera_id] = None
                self._dropped[camera_id] = self._dropped.get(camera_id, 0) + 1
                continue
            self._slots[camera_id] = None
            return packet
        return None

    @staticmethod
    def _rotated_order(camera_order: list[str], last_camera_id: str | None) -> list[str]:
        if not camera_order or last_camera_id not in camera_order:
            return camera_order
        start = (camera_order.index(last_camera_id) + 1) % len(camera_order)
        return camera_order[start:] + camera_order[:start]


@dataclass(frozen=True)
class CameraDeviceInfo:
    label: str
    stable_path: str
    video_node: str
    manufacturer: str
    model: str
    resolution: str
    status: str


def is_network_camera_source(source: str | None) -> bool:
    if not source:
        return False
    return urlparse(source).scheme.lower() in {"rtsp", "rtsps", "http", "https"}


def camera_source_kind(source: str | None) -> str:
    if not source:
        return "UNCONFIGURED"
    if is_network_camera_source(source):
        return "RTSP" if source.lower().startswith(("rtsp://", "rtsps://")) else "HTTP"
    return "USB"


def _safe_source_for_log(source: str) -> str:
    if not is_network_camera_source(source):
        return source
    parsed = urlparse(source)
    host = parsed.hostname or "camera"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


def _safe_resolve(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _device_busy(path: str) -> bool:
    try:
        result = subprocess.run(["fuser", path], capture_output=True, text=True, timeout=1)
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def _format_summary(video_node: str) -> str:
    try:
        result = subprocess.run(["v4l2-ctl", "-d", video_node, "--list-formats-ext"], capture_output=True, text=True, timeout=3)
    except Exception:
        return "Aufloesung unbekannt"
    if result.returncode != 0:
        return "Aufloesung unbekannt"
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Size: Discrete"):
            return line.replace("Size: Discrete", "").strip()
    return "Aufloesung unbekannt"


def _is_usb_frame_capture_device(video_node: str) -> bool:
    try:
        info = subprocess.run(["v4l2-ctl", "-d", video_node, "--info"], capture_output=True, text=True, timeout=2)
        formats = subprocess.run(["v4l2-ctl", "-d", video_node, "--list-formats-ext"], capture_output=True, text=True, timeout=3)
    except Exception:
        return False
    if info.returncode != 0 or formats.returncode != 0:
        return False
    if "Driver name      : uvcvideo" not in info.stdout and "Bus info         : usb" not in info.stdout:
        return False
    if "Device Caps" in info.stdout and "Metadata Capture" in info.stdout and "Video Capture\n" not in info.stdout:
        return False
    return "Size: Discrete" in formats.stdout


def _name_parts(stable_path: str) -> tuple[str, str]:
    name = Path(stable_path).name
    if "Logitech" in name or "046d" in name:
        return "Logitech", "C920" if "C920" in name or "HD_Pro_Webcam" in name else name
    if "usb" in name:
        return "USB", name
    return "Kamera", name


def discover_cameras() -> list[str]:
    return [device.video_node for device in discover_camera_devices()]


def discover_camera_devices() -> list[CameraDeviceInfo]:
    by_id = Path("/dev/v4l/by-id")
    by_path = Path("/dev/v4l/by-path")
    stable_by_node: dict[str, str] = {}
    path_by_node: dict[str, str] = {}
    for root in (by_id, by_path):
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.exists() or not path.name.endswith("video-index0"):
                continue
            if root == by_path and "usb" not in path.name:
                continue
            node = _safe_resolve(path)
            if not node.startswith("/dev/video"):
                continue
            if root == by_id:
                stable_by_node.setdefault(node, str(path))
            else:
                path_by_node.setdefault(node, str(path))
    for node, stable in path_by_node.items():
        stable_by_node.setdefault(node, stable)
    for candidate in sorted(Path("/dev").glob("video*"), key=lambda value: int(value.name.replace("video", "") or 999)):
        node = str(candidate)
        if node not in stable_by_node and _is_usb_frame_capture_device(node):
            stable_by_node[node] = node

    devices: list[CameraDeviceInfo] = []
    for node in sorted(stable_by_node, key=lambda value: int(value.replace("/dev/video", "") or 999)):
        stable = stable_by_node[node]
        manufacturer, model = _name_parts(stable)
        resolution = _format_summary(node)
        status = "belegt" if _device_busy(node) else "frei"
        port = path_by_node.get(node, stable)
        label = f"{manufacturer} {model} - {port} - {node} - {resolution} - {status}"
        devices.append(CameraDeviceInfo(label, stable, node, manufacturer, model, resolution, status))
    return devices


def open_camera_source(source: str, *, timeout_ms: int = 5000) -> cv2.VideoCapture:
    """Use the same bounded RTSP-over-TCP configuration for test and runtime.

    OpenCV FFmpeg honors OPENCV_FFMPEG_CAPTURE_OPTIONS at stream creation.
    Respect operator overrides. Never log the credential-bearing URL.
    """
    if is_network_camera_source(source):
        if source.lower().startswith(("rtsp://", "rtsps://")):
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        return cv2.VideoCapture(
            source, cv2.CAP_FFMPEG,
            [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000,
            ],
        )
    if source.isdigit():
        return cv2.VideoCapture(int(source), cv2.CAP_V4L2)
    return cv2.VideoCapture(source, cv2.CAP_V4L2)


class CameraCapture(Thread):
    """Capture worker supporting local V4L2 and WLAN/IP camera streams.

    Network streams are opened with FFmpeg where available. The worker always
    reconnects after read/open failure and feeds only the newest frame to the
    inference pipeline, so a stalled WLAN camera cannot create an ever-growing
    latency backlog.
    """

    def __init__(self, config: CameraConfig, output: LatestFrameHub, stop_event: Event, frame_callback: FramePacketCallback | None = None) -> None:
        super().__init__(daemon=True, name=f"capture-{config.camera_id}")
        self.config = config
        self.output = output
        self.stop_event = stop_event
        self.frame_callback = frame_callback
        self.stats = CameraStats()
        self._frame_id = 0
        self._reconnect_delay_seconds = 1.0
        self._max_reconnect_delay_seconds = 12.0

    def run(self) -> None:
        while not self.stop_event.is_set():
            source = self.config.device or self._default_device()
            if source is None:
                self.stats.connected = False
                self.stats.state = "OFFLINE"
                self.stats.last_error = "No camera source configured or discovered"
                self.stop_event.wait(1.0)
                continue
            self.stats.source = _safe_source_for_log(source)
            self.stats.transport = camera_source_kind(source)
            self.stats.state = "CONNECTING" if self.stats.reconnect_count == 0 else "RECONNECTING"
            try:
                capture = self._open_capture(source)
            except (OSError, cv2.error, TypeError, ValueError) as exc:
                self._mark_failure(
                    f"Videoöffnung fehlgeschlagen ({type(exc).__name__}); Netzwerk/RTSP prüfen"
                )
                self.stop_event.wait(self._reconnect_delay_seconds)
                self._reconnect_delay_seconds = min(
                    self._max_reconnect_delay_seconds, self._reconnect_delay_seconds * 1.8
                )
                continue
            try:
                if not capture.isOpened():
                    self._mark_failure("RTSP-Zugriff nicht möglich: IP, Port, RTSP-Aktivierung oder Login prüfen")
                else:
                    self._configure_capture(capture, source)
                    # isOpened() alone is NOT proof that an RTSP stream sends frames.
                    self._capture_loop(capture)
            finally:
                capture.release()
                if self.stats.connected:
                    self.stats.reconnect_count += 1
                self.stats.connected = False
                if not self.stop_event.is_set():
                    self.stats.state = "RECONNECTING"
                    self.stop_event.wait(self._reconnect_delay_seconds)
                    self._reconnect_delay_seconds = min(
                        self._max_reconnect_delay_seconds,
                        self._reconnect_delay_seconds * 1.8,
                    )
        self.stats.state = "OFFLINE"

    def _open_capture(self, source: str) -> cv2.VideoCapture:
        return open_camera_source(source, timeout_ms=5000)

    def _configure_capture(self, capture: cv2.VideoCapture, source: str) -> None:
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if is_network_camera_source(source):
            return
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        capture.set(cv2.CAP_PROP_FPS, self.config.fps)

    def _mark_failure(self, message: str) -> None:
        self.stats.connected = False
        self.stats.fps = 0.0
        self.stats.state = "RECONNECTING"
        self.stats.last_error = message
        self.stats.reconnect_count += 1
        LOGGER.error("%s: %s", self.config.camera_id, message)

    def _capture_loop(self, capture: cv2.VideoCapture) -> None:
        last_tick = monotonic()
        frames = 0
        while not self.stop_event.is_set():
            ok, image = capture.read()
            if not ok or image is None or image.size == 0:
                self.stats.decode_errors += 1
                self.stats.connected = False
                self.stats.fps = 0.0
                self.stats.last_error = "RTSP-Stream liefert keine Bilder; überprüfe Stream-Profil, Login, Netzwerk"
                LOGGER.error("%s: %s", self.config.camera_id, self.stats.last_error)
                break
            if not self.stats.connected:
                self.stats.connected = True
                self.stats.state = "ONLINE"
                self.stats.last_error = ""
                self.stats.connected_since = time()
                self._reconnect_delay_seconds = 1.0
            self._frame_id += 1
            captured_at = time()
            self.stats.frame_height, self.stats.frame_width = image.shape[:2]
            self.stats.last_frame_time = captured_at
            packet = FramePacket.from_image(self.config.camera_id, self._frame_id, image, captured_at)
            if self.output.put(packet):
                self.stats.dropped_frames += 1
                self.stats.queue_replacements += 1
            if self.frame_callback:
                try:
                    self.frame_callback(packet)
                except Exception:
                    LOGGER.exception("FRAME_CALLBACK_FAILED camera=%s frame=%s", self.config.camera_id, self._frame_id)
            frames += 1
            now = monotonic()
            if now - last_tick >= 1.0:
                self.stats.fps = frames / (now - last_tick)
                frames = 0
                last_tick = now

    def _default_device(self) -> str | None:
        devices = discover_cameras()
        if self.config.camera_id.endswith("1") and devices:
            return devices[0]
        if self.config.camera_id.endswith("2") and len(devices) > 1:
            return devices[1]
        return None
