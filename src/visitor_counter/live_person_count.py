"""Fresh YOLO observations, deliberately independent of occupancy and identities."""
from __future__ import annotations

import math
from dataclasses import dataclass
from time import time
from typing import Any

LIVE_PERSON_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class LivePersonCount:
    total: int | None
    cameras: dict[str, int | None]
    names: dict[str, str]
    state: str


def live_person_count(
    payload: dict[str, Any] | None, *, now: float | None = None,
    timeout: float = LIVE_PERSON_TIMEOUT_SECONDS,
) -> LivePersonCount:
    """Sum current per-camera YOLO results; never claim cross-camera deduplication."""
    now = time() if now is None else now
    payload = payload if isinstance(payload, dict) else {}
    raw_cameras = payload.get("cameras", [])
    cameras = [c for c in raw_cameras if isinstance(c, dict)] if isinstance(raw_cameras, list) else []
    names = {str(c.get("camera_id")): str(c.get("name") or c.get("camera_id")) for c in cameras}
    counts: dict[str, int | None] = {key: None for key in names}
    runtime = payload.get("runtime", {})
    try:
        elapsed = now - float(payload.get("timestamp", 0))
    except (ValueError, TypeError):
        elapsed = math.inf
    fresh_status = math.isfinite(elapsed) and -1 <= elapsed < timeout
    enabled = (isinstance(runtime, dict) and runtime.get("detector_active") is True
               and runtime.get("detector_enabled") is not False)
    if not fresh_status or not enabled:
        return LivePersonCount(None, counts, names, "unavailable")
    for camera in cameras:
        key = str(camera.get("camera_id"))
        try:
            age = float(camera["seconds_since_last_ai_frame"]) + max(0.0, elapsed)
            raw = camera["ai_raw_person_detections"]
            value = int(raw)
            valid_count = not isinstance(raw, bool) and value == raw and value >= 0
            processed = int(camera.get("ai_processed_frames", 0)) > 0
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if (camera.get("status") == "ONLINE" and camera.get("inference_status") == "active"
                and not camera.get("obstructed") and processed and valid_count
                and math.isfinite(age) and 0 <= age < timeout):
            counts[key] = value
    available = [value for value in counts.values() if value is not None]
    complete = bool(counts) and len(available) == len(counts)
    return LivePersonCount(
        sum(available) if complete else None, counts, names,
        "available" if complete else ("partial" if available else "unavailable"),
    )
