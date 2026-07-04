from __future__ import annotations

import argparse
from pathlib import Path

from training.scripts.common import sha256_file, utc_now, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HEF metadata with HailoRT Python bindings.")
    parser.add_argument("--hef", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("training/hailo/artifacts/hef_verification.json"))
    args = parser.parse_args()
    if not args.hef.exists() or args.hef.is_symlink() or args.hef.stat().st_size == 0:
        raise RuntimeError("HEF must be a non-empty regular file, not a symlink.")
    import hailo_platform

    hef = hailo_platform.HEF(str(args.hef))
    inputs = hef.get_input_vstream_infos()
    outputs = hef.get_output_vstream_infos()
    report = {
        "created_at": utc_now(),
        "hef": str(args.hef),
        "hef_sha256": sha256_file(args.hef),
        "inputs": [{"name": item.name, "shape": getattr(item, "shape", None)} for item in inputs],
        "outputs": [{"name": item.name, "shape": getattr(item, "shape", None)} for item in outputs],
        "architecture_required": "HAILO10H",
        "class_names": ["person"],
        "model_type": "Detection",
    }
    write_json(args.report, report)
    print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
