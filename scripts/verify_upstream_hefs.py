#!/usr/bin/env python3
"""CI check: stream official Hailo model binaries and verify pinned SHA-256."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = [
    ("yolo26m_detection_hailo10h_manifest.json", "hef_source_url"),
    ("osnet_x1_0_hailo10h_manifest.json", "source_url"),
]
HOST = "hailo-model-zoo.s3.eu-west-2.amazonaws.com"


def main() -> int:
    failures = 0
    for filename, url_key in MANIFESTS:
        manifest = json.loads((ROOT / "models" / "manifests" / filename).read_text())
        url, expected = manifest[url_key], manifest["hef_sha256"].lower()
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != HOST:
            print(f"FAIL {filename}: unapproved host")
            failures += 1
            continue
        for attempt in range(1, 3):
            digest = hashlib.sha256()
            size = 0
            try:
                with urlopen(
                    Request(url, headers={"User-Agent": "Personenzaehler-CI-Model-Integrity/1"}),
                    timeout=45,
                ) as response:
                    if urlsplit(response.geturl()).hostname != HOST:
                        raise RuntimeError("Unexpected redirect")
                    while chunk := response.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                        if size > 2_000_000_000:
                            raise RuntimeError("Oversized HEF")
                if size < 1024:
                    raise RuntimeError("Truncated HEF")
                actual = digest.hexdigest()
                if actual != expected:
                    raise RuntimeError(f"SHA-256 mismatch: {actual}; expected {expected}")
                print(f"OK {filename}: {size} bytes SHA-256 {actual}")
                break
            except Exception as exc:
                print(f"FAIL attempt={attempt} {filename}: {exc}")
                if attempt == 2:
                    failures += 1
                else:
                    time.sleep(2)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
