import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from visitor_counter.application_service import DashboardSnapshot
from visitor_counter.desktop.pages import OverviewPage
from visitor_counter.live_person_count import live_person_count


def observation(count, timestamp=100):
    return {"timestamp": timestamp, "runtime": {"detector_active": True},
            "cameras": [{"camera_id": "camera_1", "name": "Augen 1", "status": "ONLINE",
                         "inference_status": "active", "ai_processed_frames": 50,
                         "seconds_since_last_ai_frame": .1, "ai_raw_person_detections": count}]}


def test_overview_changes_yolo_count_without_rewriting_occupancy_and_clears_expired_results(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    try:
        page.update_snapshot(DashboardSnapshot(timestamp=100, counts={
            "inside": 1, "entered": 1, "exited": 1, "throughput": 2,
            "occupancy_adjustment": 1,
        }))
        for count in [2, 1, 0]:
            page.update_live_people(live_person_count(observation(count), now=100.5))
            assert page.live_people_metric.value_label.text() == str(count)
            assert f"Augen 1: {count}" in page.live_people_metric.detail_label.text()
            assert page.metrics["inside"].value_label.text() == "1"
        page.update_live_people(live_person_count(observation(2), now=103))
        assert page.live_people_metric.value_label.text() == "Nicht verfügbar"
        assert page.metrics["inside"].value_label.text() == "1"
        assert "+1" in page.metrics["inside"].toolTip()
        assert "doppelt enthalten" in page.live_people_metric.detail_label.text()
    finally:
        page.close()
        app.processEvents()
