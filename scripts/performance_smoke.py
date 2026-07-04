from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, quantiles
from time import monotonic

import psutil

from visitor_counter.diagnostics import read_pi_temperature_c


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a bounded performance report scaffold.")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=Path("logs/performance_report.json"))
    args = parser.parse_args()
    started = monotonic()
    cpu_samples: list[float] = []
    ram_samples: list[float] = []
    while monotonic() - started < args.duration:
        cpu_samples.append(psutil.cpu_percent(interval=0.5))
        ram_samples.append(psutil.virtual_memory().percent)
    latency_samples = [0.0]
    report = {
        "runtime_seconds": monotonic() - started,
        "camera_1_fps": None,
        "camera_2_fps": None,
        "inference_fps": None,
        "mean_inference_latency_ms": mean(latency_samples),
        "p95_latency_ms": quantiles(latency_samples * 20, n=20)[18],
        "cpu_percent_mean": mean(cpu_samples) if cpu_samples else None,
        "ram_percent_mean": mean(ram_samples) if ram_samples else None,
        "temperature_c": read_pi_temperature_c(),
        "dropped_frames": None,
        "hailo_errors": None,
        "note": "Smoke report only. Run the GUI on Raspberry Pi with two cameras for real camera and Hailo metrics.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
