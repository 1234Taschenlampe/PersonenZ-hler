"""Counting readiness is separate from API liveness and tolerates one camera."""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import scripts.status_api as status_api
from visitor_counter.configuration import AppConfig


def _config() -> AppConfig:
    config = AppConfig()
    config.cameras["camera_1"].device = "rtsp://example.invalid/Preview_01_main"
    config.cameras["camera_2"].device = "rtsp://example.invalid/Preview_01_main"
    return config


def _camera(camera_id: str, *, age: float = 0.5, state: str = "ONLINE") -> dict:
    return {
        "camera_id": camera_id,
        "status": state,
        "inference_status": "active" if state == "ONLINE" else "waiting",
        "seconds_since_last_ai_frame": age,
        "ai_processed_frames": 10,
    }


def test_readiness_requires_recent_real_inference_not_just_camera_fps() -> None:
    config = _config()
    assert status_api.counting_readiness(None, config)["ready"] is False
    live = {
        "runtime": {"detector_active": True},
        "cameras": [_camera("camera_1", age=12.0), _camera("camera_2", state="RECONNECTING")],
    }
    status = status_api.counting_readiness(live, config)
    assert (status["state"], status["reason"]) == ("unavailable", "no_recent_ai_frames")


def test_readiness_survives_single_camera_mode_and_reports_degradation() -> None:
    config = _config()
    live = {
        "runtime": {"detector_active": True},
        "cameras": [_camera("camera_1"), _camera("camera_2", state="OFFLINE")],
    }
    status = status_api.counting_readiness(live, config)
    assert status["ready"]
    assert status["state"] == "degraded"
    assert (status["active_camera_count"], status["configured_camera_count"]) == (1, 2)

    config.cameras["camera_2"].device = None
    status = status_api.counting_readiness(live, config)
    assert status["ready"] and status["state"] == "ready"


def test_paused_detector_not_reported_healthy() -> None:
    config = _config()
    config.model.detector_enabled = False
    status = status_api.counting_readiness(
        {"runtime": {"detector_active": True},
         "cameras": [_camera("camera_1"), _camera("camera_2")]},
        config,
    )
    assert not status["ready"]
    assert status["state"] == "paused"


def test_readiness_endpoint_is_authenticated_and_uses_503_when_degraded_to_zero(monkeypatch):
    status_api.StatusHandler.app_config = _config()
    status_api.StatusHandler.tokens = {
        "viewer": "v" * 32, "operator": "o" * 32, "admin": "a" * 32,
    }
    response = {"readiness": {"ready": False, "state": "unavailable"}}
    monkeypatch.setattr(status_api, "cached_status", lambda *_args, **_kwargs: response)
    server = ThreadingHTTPServer(("127.0.0.1", 0), status_api.StatusHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/v1/readiness"
    try:
        try:
            urlopen(url, timeout=3)
        except HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("readiness without a token was allowed")

        request = Request(url, headers={"Authorization": "Bearer " + "v" * 32})
        try:
            urlopen(request, timeout=3)
        except HTTPError as exc:
            assert exc.code == 503
            assert json.loads(exc.read())["state"] == "unavailable"
        else:
            raise AssertionError("unhealthy inference returned HTTP 200")

        response["readiness"] = {"ready": True, "state": "degraded"}
        with urlopen(request, timeout=3) as good:
            assert good.status == 200
            assert json.loads(good.read())["state"] == "degraded"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
