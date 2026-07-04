from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import sha256_file, utc_now, write_json


def choose_split(session: str, index: int) -> str:
    bucket = index % 20
    if bucket < 14:
        return "train"
    if bucket < 17:
        return "val"
    return "test"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create leakage-safe split manifest by session/scenario.")
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("training/dataset/split_manifest.json"))
    args = parser.parse_args()
    manifests = sorted(args.sessions.rglob("capture_manifest.json"))
    items: list[dict] = []
    for index, manifest_path in enumerate(manifests):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        split = choose_split(manifest_path.parent.name, index)
        for item in data.get("items", []):
            file_path = Path(item["file"])
            label_path = file_path.with_suffix(".txt")
            label_count = 0
            if label_path.exists():
                label_count = len([line for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()])
            items.append(
                {
                    "source_file": str(file_path),
                    "camera": item.get("camera_id"),
                    "capture_time": item.get("utc"),
                    "scenario": item.get("scenario"),
                    "split": split,
                    "image_sha256": sha256_file(file_path) if file_path.exists() else None,
                    "label_count": label_count,
                    "session": manifest_path.parent.name,
                }
            )
    write_json(args.output, {"created_at": utc_now(), "items": items})
    print(f"items={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
