from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from threading import Condition, Event, Thread
from time import monotonic, sleep, time
from typing import Callable

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

    def get_next(
        self,
        camera_order: list[str],
        last_camera_id: str | None = None,
        timeout: float = 0.2,
        max_age_seconds: float | None = None,
    ) -> FramePacket | None:
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

    def _take_ready(
        self,
        camera_order: list[str],
        last_camera_id: str | None,
        max_age_seconds: float | None,
    ) -> FramePacket | None:
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

    def _rotated_order(self, camera_order: list[str], last_camera_id: str | None) -> list[str]:
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
        result = subprocess.run(
            ["v4l2-ctl", "-d", video_node, "--list-formats-ext"],
            capture_output=True,
            text=True,
            timeout=3,
        )
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
        formats = subprocess.run(
            ["v4l2-ctl", "-d", video_node, "--list-formats-ext"],
            capture_output=True,
            text=True,
            timeout=3,
        )
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
        devices.append(
            CameraDeviceInfo(
                label=label,
                stable_path=stable,
                video_node=node,
                manufacturer=manufacturer,
                model=model,
                resolution=resolution,
                status=status,
            )
        )
    return devices


class CameraCapture(Thread):
    def __init__(
        self,
        config: CameraConfig,
        output: LatestFrameHub,
        stop_event: Event,
        frame_callback: FramePacketCallback | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"capture-{config.camera_id}")
        self.config = config
        self.output = output
        self.stop_event = stop_event
        self.frame_callback = frame_callback
        self.stats = CameraStats()
        self._frame_id = 0

    def run(self) -> None:
        while not self.stop_event.is_set():
            device = self.config.device or self._default_device()
            if device is None:
                self.stats.connected = False
                self.stats.last_error = "No camera device configured or discovered"
                sleep(1.0)
                continue
            capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
            try:
                if not capture.isOpened():
                    self.stats.connected = False
                    self.stats.last_error = f"Cannot open camera {device}"
                    LOGGER.error(self.stats.last_error)
                    sleep(1.0)
                    continue
                capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
                capture.set(cv2.CAP_PROP_FPS, self.config.fps)
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.stats.connected = True
                self._capture_loop(capture)
            finally:
                capture.release()
                self.stats.connected = False

    def _capture_loop(self, capture: cv2.VideoCapture) -> None:
        last_tick = monotonic()
        frames = 0
        while not self.stop_event.is_set():
            ok, image = capture.read()
            if not ok:
                self.stats.last_error = "Camera read failed; reconnecting"
                LOGGER.error("%s: %s", self.config.camera_id, self.stats.last_error)
                break
            self._frame_id += 1
            packet = FramePacket.from_image(self.config.camera_id, self._frame_id, image, time())
            if self.output.put(packet):
                self.stats.dropped_frames += 1
                self.stats.queue_replacements += 1
            if self.frame_callback:
                try:
                    self.frame_callback(packet)
                except Exception:
                    LOGGER.exception("FRAME_CALLBACK_FAILED camera=%s frame=%s", self.config.camera_id, self._frame_id)
            if self._frame_id % 30 == 0:
                LOGGER.info(
                    "CAMERA_CAPTURE camera=%s frame=%s shape=%sx%s timestamp=%.3f",
                    self.config.camera_id,
                    self._frame_id,
                    packet.width,
                    packet.height,
                    packet.captured_at,
                )
                LOGGER.info("FRAME_PUBLISH camera=%s frame=%s", self.config.camera_id, self._frame_id)
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
