from __future__ import annotations

import argparse
import inspect
from pathlib import Path

import yaml

from common import run_command, sha256_file, utc_now, write_json


def assert_gpu_available() -> None:
    result = run_command(["nvidia-smi"])
    if result.get("returncode") != 0:
        raise RuntimeError("NVIDIA GPU is required for training; nvidia-smi failed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune official YOLO26x for one person class.")
    parser.add_argument("--config", type=Path, default=Path("training/configs/yolo26x_person_640.yaml"))
    parser.add_argument("--data", type=Path, default=Path("training/dataset/dataset.yaml"))
    parser.add_argument("--weights", type=Path, default=Path("models/yolo26x.pt"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    assert_gpu_available()
    from ultralytics import YOLO

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    cfg["model"] = str(args.weights)
    cfg["data"] = str(args.data)
    cfg["seed"] = args.seed
    cfg["name"] = f"yolo26x_person_{cfg['imgsz']}_seed{args.seed}"
    supported = set(inspect.signature(YOLO.train).parameters)
    unknown = set(cfg) - supported - {"model"}
    if unknown:
        raise RuntimeError(f"Unsupported Ultralytics train args: {sorted(unknown)}")
    manifest = {
        "created_at": utc_now(),
        "config": cfg,
        "weights_sha256": sha256_file(args.weights),
        "git": run_command(["git", "rev-parse", "HEAD"]),
        "nvidia_smi": run_command(["nvidia-smi"]),
        "pip_freeze": run_command(["python", "-m", "pip", "freeze"]),
    }
    write_json(Path("training/runs") / cfg["name"] / "run_manifest.json", manifest)
    if args.dry_run:
        print("dry-run ok")
        return 0
    model = YOLO(str(args.weights))
    model.train(**{k: v for k, v in cfg.items() if k != "model"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
