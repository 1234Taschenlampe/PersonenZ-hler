from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import cv2

from common import utc_now, write_json


def validate_label_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return ["missing label file"]
    seen: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            errors.append(f"line {line_no}: expected 5 fields")
            continue
        if parts[0] != "0":
            errors.append(f"line {line_no}: invalid class {parts[0]}")
        try:
            _, x, y, w, h = [float(part) for part in parts]
        except ValueError:
            errors.append(f"line {line_no}: non-numeric field")
            continue
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
            errors.append(f"line {line_no}: box outside normalized range")
        if w < 0.002 or h < 0.002:
            errors.append(f"line {line_no}: extremely small box")
        key = " ".join(parts)
        if key in seen:
            errors.append(f"line {line_no}: duplicate box")
        seen.add(key)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate YOLO person-only labels.")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/label_validation.json"))
    args = parser.parse_args()
    issues: list[dict] = []
    stats = Counter()
    for image_path in sorted(args.images.rglob("*.jpg")):
        image = cv2.imread(str(image_path))
        if image is None:
            issues.append({"file": str(image_path), "errors": ["corrupt image"]})
            continue
        label_path = args.labels / image_path.relative_to(args.images).with_suffix(".txt")
        errors = validate_label_file(label_path)
        if errors:
            issues.append({"file": str(image_path), "label": str(label_path), "errors": errors})
        stats["images"] += 1
        if label_path.exists() and label_path.read_text(encoding="utf-8").strip():
            stats["positive_images"] += 1
            stats["boxes"] += len([line for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()])
        else:
            stats["negative_images"] += 1
    report = {"created_at": utc_now(), "stats": dict(stats), "issues": issues}
    write_json(args.report, report)
    print(f"images={stats['images']} issues={len(issues)}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
