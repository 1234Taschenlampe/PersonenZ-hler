#!/usr/bin/env python3
import json
import os
import threading
import time
import urllib.request
from urllib.parse import urlparse

import cv2
import numpy as np


BASE_URL = os.environ.get("VISITOR_COUNTER_BASE_URL", "https://personenzaehler.local:8766").rstrip("/")
ACCESS_TOKEN = os.environ.get("VISITOR_COUNTER_OPERATOR_TOKEN", "")
WINDOW_NAME = "KI Besucherzaehler Monitor"
FRAME_DELAY_SECONDS = 0.50


class MjpegStream(threading.Thread):
    def __init__(self, url: str):
        super().__init__(daemon=True)
        self.url = url
        self.frame = None
        self.error = "warte auf Stream"
        self.running = True
        self._lock = threading.Lock()

    def run(self) -> None:
        while self.running:
            try:
                with urllib.request.urlopen(authenticated_request(self.url), timeout=8) as stream:
                    data = b""
                    self.error = ""
                    while self.running:
                        data += stream.read(8192)
                        start = data.find(b"\xff\xd8")
                        end = data.find(b"\xff\xd9", start + 2)
                        if start != -1 and end != -1:
                            jpg = data[start : end + 2]
                            data = data[end + 2 :]
                            frame = cv2.imdecode(
                                np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR
                            )
                            if frame is not None:
                                with self._lock:
                                    self.frame = frame
                                time.sleep(FRAME_DELAY_SECONDS)
            except Exception as exc:
                self.error = str(exc)
                time.sleep(1)

    def snapshot(self):
        with self._lock:
            return None if self.frame is None else self.frame.copy()


class StatusPoller(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.status = {}
        self.error = "warte auf API"
        self.running = True

    def run(self) -> None:
        while self.running:
            try:
                with urllib.request.urlopen(authenticated_request(f"{BASE_URL}/api/v1/status"), timeout=3) as response:
                    self.status = json.loads(response.read().decode("utf-8"))
                self.error = ""
            except Exception as exc:
                self.error = str(exc)
            time.sleep(1)


def fit_frame(frame, size):
    width, height = size
    if frame is None:
        return np.zeros((height, width, 3), dtype=np.uint8)
    h, w = frame.shape[:2]
    scale = min(width / w, height / h)
    new_size = (int(w * scale), int(h * scale))
    resized = cv2.resize(frame, new_size)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    x = (width - new_size[0]) // 2
    y = (height - new_size[1]) // 2
    canvas[y : y + new_size[1], x : x + new_size[0]] = resized
    return canvas


def put_text(img, text, pos, scale=1.0, color=(255, 255, 255), thickness=2):
    cv2.putText(
        img,
        text,
        pos,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def main() -> int:
    parsed = urlparse(BASE_URL)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    ):
        raise RuntimeError("Monitor connections must use HTTPS, except on loopback.")
    if len(ACCESS_TOKEN) < 32:
        raise RuntimeError("VISITOR_COUNTER_OPERATOR_TOKEN must contain at least 32 characters.")
    streams = {
        "Eingang": MjpegStream(f"{BASE_URL}/api/v1/video/camera_1.mjpg"),
        "Ausgang": MjpegStream(f"{BASE_URL}/api/v1/video/camera_2.mjpg"),
    }
    status = StatusPoller()
    for stream in streams.values():
        stream.start()
    status.start()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1920, 1080)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    while True:
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        canvas[:] = (24, 29, 27)

        counters = status.status.get("counters", {})
        cameras = status.status.get("cameras", {})
        inside = counters.get("current_inside", 0)
        entries = counters.get("daily_entries", 0)
        exits = counters.get("daily_exits", 0)
        unique = counters.get("daily_unique_visitors", 0)

        cv2.rectangle(canvas, (0, 0), (1920, 155), (38, 108, 88), -1)
        put_text(canvas, "KI Besucherzaehler", (34, 52), 1.35, (245, 247, 244), 3)
        put_text(canvas, f"Aktuell innen: {inside}", (34, 118), 1.75, (235, 185, 73), 4)
        put_text(canvas, f"Eintritte: {entries}", (690, 62), 1.0)
        put_text(canvas, f"Austritte: {exits}", (690, 112), 1.0)
        put_text(canvas, f"Besucher heute: {unique}", (1010, 62), 1.0)

        api_text = "API OK" if not status.error else f"API: {status.error[:55]}"
        put_text(canvas, api_text, (1010, 112), 0.8, (210, 232, 226), 2)

        panel_w, panel_h = 900, 790
        positions = {"Eingang": (40, 235), "Ausgang": (980, 235)}
        for name, stream in streams.items():
            x, y = positions[name]
            cv2.rectangle(canvas, (x - 8, y - 58), (x + panel_w + 8, y + panel_h + 8), (244, 239, 230), 3)
            put_text(canvas, name, (x, y - 18), 1.25, (245, 247, 244), 3)

            cam_key = "entrance" if name == "Eingang" else "exit"
            cam = cameras.get(cam_key, {})
            cam_state = "Kamera OK" if cam.get("healthy") else "Kamera wartet"
            put_text(canvas, cam_state, (x + 630, y - 18), 0.8, (210, 232, 226), 2)

            frame = fit_frame(stream.snapshot(), (panel_w, panel_h))
            canvas[y : y + panel_h, x : x + panel_w] = frame
            if stream.frame is None:
                put_text(canvas, stream.error[:60], (x + 40, y + 390), 0.8, (235, 185, 73), 2)

        put_text(canvas, "Taste q beendet die Monitoransicht", (1320, 1035), 0.75, (190, 205, 198), 2)
        cv2.imshow(WINDOW_NAME, canvas)
        if cv2.waitKey(int(FRAME_DELAY_SECONDS * 1000)) & 0xFF == ord("q"):
            break

    status.running = False
    for stream in streams.values():
        stream.running = False
    cv2.destroyAllWindows()
    return 0


def authenticated_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})


if __name__ == "__main__":
    raise SystemExit(main())
