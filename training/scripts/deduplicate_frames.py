from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from common import sha256_file, utc_now, write_json


def phash(path: Path) -> int:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"Cannot read image: {path}")
    resized = cv2.resize(image, (32, 32))
    dct = cv2.dct(np.float32(resized))
    low = dct[:8, :8]
    median = float(np.median(low[1:, 1:]))
    bits = low > median
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming(a: int, b: int) -> int:
    return int((a ^ b).bit_count())


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove near-duplicate images using perceptual hashes.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    kept: list[dict] = []
    hashes: list[int] = []
    duplicates: list[dict] = []
    for path in sorted(args.input.rglob("*.jpg")):
        value = phash(path)
        if any(hamming(value, existing) <= args.threshold for existing in hashes):
            duplicates.append({"file": str(path), "phash": f"{value:016x}"})
            continue
        hashes.append(value)
        target = args.output / path.name
        target.write_bytes(path.read_bytes())
        kept.append({"file": str(target), "source": str(path), "phash": f"{value:016x}", "sha256": sha256_file(target)})
    write_json(args.output / "deduplicate_manifest.json", {"created_at": utc_now(), "kept": kept, "duplicates": duplicates})
    print(f"kept={len(kept)} duplicates={len(duplicates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
