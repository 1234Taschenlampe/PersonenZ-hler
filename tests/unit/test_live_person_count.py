import copy

import pytest

from visitor_counter.live_person_count import live_person_count


def payload(first=1, second=0):
    return {
        "timestamp": 100.0,
        "runtime": {"detector_active": True, "detector_enabled": True},
        "counts": {"inside": 37, "visible": 1},
        "cameras": [
            {"camera_id": name, "name": name, "status": "ONLINE",
             "inference_status": "active", "ai_processed_frames": 100,
             "seconds_since_last_ai_frame": .1, "ai_raw_person_detections": number}
            for name, number in [("camera_1", first), ("camera_2", second)]
        ],
    }


@pytest.mark.parametrize("first,second,total", [(2, 0, 2), (1, 0, 1), (0, 0, 0), (1, 1, 2)])
def test_current_yolo_results_are_independent_of_occupancy_and_identity(first, second, total):
    data = payload(first, second)
    before = copy.deepcopy(data)
    result = live_person_count(data, now=100.4)
    assert result.total == total
    assert result.cameras == {"camera_1": first, "camera_2": second}
    assert data == before  # Neither occupancy nor detection data is changed.


def test_timeout_uses_elapsed_wall_time_even_when_last_status_stops_updating():
    data = payload(2, 1)
    assert live_person_count(data, now=101.8).total == 3
    expired = live_person_count(data, now=102)
    assert expired.total is None and expired.state == "unavailable"
    assert set(expired.cameras.values()) == {None}


def test_one_failed_camera_does_not_masquerade_as_zero_or_a_complete_total():
    data = payload(2, 3)
    data["cameras"][1]["seconds_since_last_ai_frame"] = 7
    result = live_person_count(data, now=100.4)
    assert result.total is None and result.state == "partial"
    assert result.cameras == {"camera_1": 2, "camera_2": None}


@pytest.mark.parametrize("change", [
    {"status": "OFFLINE"}, {"inference_status": "waiting for frame"},
    {"obstructed": True}, {"ai_processed_frames": 0},
    {"ai_raw_person_detections": -1}, {"ai_raw_person_detections": True},
    {"ai_raw_person_detections": 1.5}, {"seconds_since_last_ai_frame": float("nan")},
])
def test_invalid_or_unprocessed_camera_observations_are_unavailable(change):
    data = payload()
    data["cameras"][0].update(change)
    assert live_person_count(data, now=100.4).cameras["camera_1"] is None


def test_paused_detector_and_missing_status_are_not_reported_as_zero():
    data = payload()
    data["runtime"]["detector_enabled"] = False
    assert live_person_count(data, now=100.4).total is None
    for broken in [None, {}, {"cameras": None}, {"timestamp": "invalid"}]:
        assert live_person_count(broken, now=100.4).total is None
