from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from training.scripts.common import run_command, sha256_file, utc_now, write_json


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required Hailo tool not found: {name}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile custom YOLO26x person ONNX to HAILO10H HEF.")
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--target", default="hailo10h")
    parser.add_argument("--artifacts", type=Path, default=Path("training/hailo/artifacts"))
    args = parser.parse_args()
    if args.target.lower() != "hailo10h":
        raise RuntimeError("Only HAILO10H target is allowed for this project.")
    if not args.onnx.exists():
        raise RuntimeError(f"ONNX not found: {args.onnx}")
    if not args.calibration.exists():
        raise RuntimeError(f"Calibration directory not found: {args.calibration}")
    hailomz = require_tool("hailomz")
    args.artifacts.mkdir(parents=True, exist_ok=True)
    parsed = args.artifacts / "yolo26x_person_640.fp.har"
    quant = args.artifacts / "yolo26x_person_640.quant.har"
    hef = args.artifacts / "yolo26x_person_hailo10h_640.hef"
    report = {
        "created_at": utc_now(),
        "target": "HAILO10H",
        "onnx": str(args.onnx),
        "onnx_sha256": sha256_file(args.onnx),
        "hailomz": hailomz,
        "versions": {
            "hailomz": run_command(["hailomz", "--version"]),
            "hailortcli": run_command(["hailortcli", "--version"]),
        },
        "steps": {},
    }
    report["steps"]["parse"] = run_command(
        ["hailomz", "parse", "--ckpt", str(args.onnx), "--har-path", str(parsed), "--hw-arch", "hailo10h"],
        timeout=3600,
    )
    if report["steps"]["parse"].get("returncode") != 0:
        write_json(args.artifacts / "compiler_report.json", report)
        raise RuntimeError("Hailo parse failed; inspect compiler_report.json")
    report["steps"]["optimize"] = run_command(
        ["hailomz", "optimize", "--har", str(parsed), "--calib-path", str(args.calibration), "--output-har-path", str(quant)],
        timeout=7200,
    )
    if report["steps"]["optimize"].get("returncode") != 0:
        write_json(args.artifacts / "compiler_report.json", report)
        raise RuntimeError("Hailo optimize failed; inspect compiler_report.json")
    report["steps"]["compile"] = run_command(["hailomz", "compile", "--har", str(quant), "--hef-path", str(hef)], timeout=7200)
    if report["steps"]["compile"].get("returncode") != 0:
        write_json(args.artifacts / "compiler_report.json", report)
        raise RuntimeError("Hailo compile failed; inspect compiler_report.json")
    report["artifacts"] = {
        "parsed_har": str(parsed),
        "parsed_har_sha256": sha256_file(parsed),
        "quant_har": str(quant),
        "quant_har_sha256": sha256_file(quant),
        "hef": str(hef),
        "hef_sha256": sha256_file(hef),
    }
    write_json(args.artifacts / "compiler_report.json", report)
    print(hef)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
