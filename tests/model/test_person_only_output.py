from __future__ import annotations

import yaml


def test_dataset_is_person_only() -> None:
    data = yaml.safe_load(open("training/dataset/dataset.yaml", encoding="utf-8"))
    assert data["nc"] == 1
    assert data["names"] == {0: "person"}
