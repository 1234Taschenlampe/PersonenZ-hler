"""Offline unit tests for cautious automatic GitHub deployments."""
from __future__ import annotations

import io
import json

import pytest

from scripts import update_safety


def test_ci_gates_on_matching_successful_github_actions_checks(monkeypatch):
    def run(name, conclusion="success", slug="github-actions"):
        return {"name": name, "status": "completed",
                "conclusion": conclusion, "app": {"slug": slug}}

    jobs = [run("test (3.11)"), run("test (3.12)"), run("package")]

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(update_safety.urllib.request, "urlopen",
                        lambda *_args, **kwargs:
                        Response(json.dumps({"check_runs": jobs}).encode()))
    assert update_safety.ci_approved("a" * 40)[0]

    jobs[1]["conclusion"] = "failure"
    approved, message = update_safety.ci_approved("a" * 40)
    assert not approved
    assert "test (3.12)" in message

    jobs[1] = run("test (3.12)", slug="unknown")
    assert not update_safety.ci_approved("a" * 40)[0]


def test_ci_fail_closed_if_unreachable(monkeypatch):
    from urllib.error import URLError

    def broken_request(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr(update_safety.urllib.request, "urlopen", broken_request)
    approved, message = update_safety.ci_approved("a" * 40)
    assert not approved
    assert "nicht pruefbar" in message
    assert not update_safety.ci_approved("not-a-sha")[0]


def test_cameras_get_healthy_only_with_fresh_status(tmp_path, monkeypatch):
    path = tmp_path / "live_status.json"
    monkeypatch.setattr(update_safety, "status_file", lambda: path)
    monkeypatch.setattr(update_safety.time, "time", lambda: 200.0)
    status = {
        "timestamp": 199.0,
        "runtime": {"detector_active": True},
        "cameras": [
            {"camera_id": "camera_1", "ai_processed_frames": 20,
             "seconds_since_last_ai_frame": 0.2, "inference_status": "active"},
            {"camera_id": "camera_2", "ai_processed_frames": 0,
             "seconds_since_last_ai_frame": None, "inference_status": "waiting"},
        ],
    }
    path.write_text(json.dumps(status))
    assert update_safety.healthy_cameras_before_update() == {"camera_1"}
    assert not update_safety.ai_recovered({"camera_1"}, 201.0)
    assert update_safety.ai_recovered({"camera_1"}, 198.0)
    assert not update_safety.ai_recovered({"camera_1", "camera_2"}, 198.0)
    status["timestamp"] = 150.0
    path.write_text(json.dumps(status))
    assert not update_safety.healthy_cameras_before_update()


def test_camera_health_requires_new_processed_frames_after_restart(tmp_path, monkeypatch):
    path = tmp_path / "live_status.json"
    monkeypatch.setattr(update_safety, "status_file", lambda: path)
    monkeypatch.setattr(update_safety.time, "time", lambda: 500.0)
    status = {
        "timestamp": 499.0,
        "runtime": {"detector_active": True},
        "cameras": [
            {"camera_id": "camera_1", "ai_processed_frames": 1,
             "seconds_since_last_ai_frame": 0.2, "inference_status": "active"},
        ],
    }
    path.write_text(json.dumps(status))
    assert not update_safety.ai_recovered({"camera_1"}, 495.0)
    status["cameras"][0]["ai_processed_frames"] = 2
    path.write_text(json.dumps(status))
    assert update_safety.ai_recovered({"camera_1"}, 495.0)


def test_service_path_mismatch_blocks_update(tmp_path, monkeypatch):
    monkeypatch.setattr(update_safety, "_run",
                        lambda *args, **kwargs: str(tmp_path / "different"))
    good, message = update_safety.service_paths_correct(
        tmp_path / "app", {"personenzaehler.service": True}
    )
    assert not good
    assert "andere Installation" in message


def test_service_path_check_ignores_non_running_units(tmp_path, monkeypatch):
    monkeypatch.setattr(update_safety, "_run",
                        lambda *args, **kwargs: pytest.fail("Must not probe stopped services"))
    assert update_safety.service_paths_correct(
        tmp_path, {"personenzaehler.service": False}
    )[0]


def test_recovery_wait_detects_missing_camera_work(monkeypatch, tmp_path):
    monkeypatch.setattr(update_safety, "ai_recovered", lambda *_args: False)
    with pytest.raises(RuntimeError, match="KI-Verarbeitung"):
        update_safety.wait_for_recovery(
            tmp_path, {"personenzaehler.service": True},
            {"camera_1"}, 0, lambda *_args: True, attempts=2, delay=0
        )


def test_recovery_wait_accepts_active_services_and_real_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(update_safety, "ai_recovered", lambda *_args: True)
    update_safety.wait_for_recovery(
        tmp_path, {"personenzaehler.service": True},
        {"camera_1"}, 0, lambda *_args: True, attempts=1, delay=0
    )
