from visitor_counter.emulator import (
    scenario_detector_outage_no_false_count,
    scenario_normal_entry,
    scenario_normal_exit,
    scenario_reid_unavailable,
    scenario_router_outage_no_false_count,
    scenario_same_person_cross_camera_reid,
    scenario_turnaround,
    scenario_two_people,
)


def test_normal_entry() -> None:
    assert scenario_normal_entry().passed


def test_normal_exit() -> None:
    assert scenario_normal_exit().passed


def test_turnaround_is_not_counted() -> None:
    assert scenario_turnaround().passed


def test_two_people_are_counted_separately() -> None:
    assert scenario_two_people().passed


def test_router_outage_does_not_create_false_count() -> None:
    assert scenario_router_outage_no_false_count().passed


def test_detector_outage_does_not_create_false_count() -> None:
    assert scenario_detector_outage_no_false_count().passed


def test_cross_camera_reid_for_same_person() -> None:
    assert scenario_same_person_cross_camera_reid().passed


def test_no_reid_does_not_merge_from_geometry_only() -> None:
    assert scenario_reid_unavailable().passed
