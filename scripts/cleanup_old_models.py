from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

MODEL_EXTENSIONS = {
    ".hef",
    ".onnx",
    ".pt",
    ".pth",
    ".weights",
    ".tflite",
    ".safetensors",
    ".torchscript",
    ".engine",
    ".blob",
}
MODEL_DIR_HINTS = {
    "models",
    "weights",
    "checkpoints",
    "ultralytics",
    "torch",
    "hub",
    "huggingface",
    "hailo_models",
    "model_zoo",
    "caches",
    "cache",
}
KEEP_NAMES = {
    "yolo26x.pt",
    "yolo26x.onnx",
    "yolo26x.har",
    "yolo26x.hef",
    "yolo26x_hailo10h_640.hef",
}
PROTECTED_PREFIXES = ("/boot", "/etc", "/lib", "/usr/lib", "/usr/share", "/bin", "/sbin")


@dataclass(frozen=True)
class ModelInventoryItem:
    path: str
    filename: str
    size_bytes: int
    modified_at: str
    extension: str
    detected_model_type: str
    reason: str


@dataclass(frozen=True)
class DeleteResult:
    path: str
    deleted: bool
    error: str | None = None


def _is_protected(path: Path) -> bool:
    resolved = str(path.resolve())
    return any(resolved == prefix or resolved.startswith(f"{prefix}/") for prefix in PROTECTED_PREFIXES)


def _detect_type(path: Path) -> tuple[str, str] | None:
    suffix = path.suffix.lower()
    parts = {part.lower() for part in path.parts}
    directory_hit = parts.intersection(MODEL_DIR_HINTS)
    if suffix in MODEL_EXTENSIONS:
        return suffix.removeprefix(".").upper(), f"extension {suffix}"
    if directory_hit and suffix in {".bin", ".param"}:
        return "MODEL_CACHE", f"directory hint {sorted(directory_hit)[0]} and extension {suffix}"
    return None


def inventory(roots: Iterable[Path]) -> list[ModelInventoryItem]:
    items: list[ModelInventoryItem] = []
    for root in roots:
        if not root.exists():
            continue
        if _is_protected(root):
            continue
        for path in root.rglob("*"):
            if any(part in {".git", ".venv", "venv", "__pycache__", "model_quarantine"} for part in path.parts):
                continue
            if not path.is_file() or _is_protected(path):
                continue
            detected = _detect_type(path)
            if detected is None:
                continue
            stat = path.stat()
            items.append(
                ModelInventoryItem(
                    path=str(path.resolve()),
                    filename=path.name,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    extension=path.suffix.lower(),
                    detected_model_type=detected[0],
                    reason=detected[1],
                )
            )
    return sorted(items, key=lambda item: item.path)


def plan_deletes(items: list[ModelInventoryItem]) -> list[ModelInventoryItem]:
    planned: list[ModelInventoryItem] = []
    for item in items:
        if item.filename in KEEP_NAMES:
            continue
        path = Path(item.path)
        parts = {part.lower() for part in path.parts}
        if not (item.extension in MODEL_EXTENSIONS or parts.intersection(MODEL_DIR_HINTS)):
            continue
        planned.append(item)
    return planned


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_files(items: list[ModelInventoryItem]) -> list[DeleteResult]:
    results: list[DeleteResult] = []
    for item in items:
        path = Path(item.path)
        try:
            if _is_protected(path):
                results.append(DeleteResult(item.path, False, "protected path"))
                continue
            path.unlink()
            results.append(DeleteResult(item.path, True, None))
        except Exception as exc:  # noqa: BLE001
            results.append(DeleteResult(item.path, False, str(exc)))
    return results


def quarantine_files(items: list[ModelInventoryItem], quarantine_dir: Path) -> list[DeleteResult]:
    results: list[DeleteResult] = []
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        source = Path(item.path)
        try:
            if _is_protected(source):
                results.append(DeleteResult(item.path, False, "protected path"))
                continue
            target_name = str(source.resolve()).lstrip("/").replace("/", "__")
            target = quarantine_dir / target_name
            counter = 1
            while target.exists():
                target = quarantine_dir / f"{target_name}.{counter}"
                counter += 1
            shutil.move(str(source), str(target))
            results.append(DeleteResult(item.path, True, f"quarantined to {target}"))
        except Exception as exc:  # noqa: BLE001
            results.append(DeleteResult(item.path, False, str(exc)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory and safely remove old AI model files.")
    parser.add_argument("--root", action="append", type=Path, default=[], help="Root to scan. Can be used multiple times.")
    parser.add_argument("--pi-defaults", action="store_true", help="Scan project plus common Raspberry Pi user model locations.")
    parser.add_argument(
        "--include-user-caches",
        action="store_true",
        help="Also scan torch, Hugging Face and Ultralytics caches under the current user home.",
    )
    parser.add_argument("--quarantine", action="store_true", help="Move planned files into model_quarantine/ instead of deleting.")
    parser.add_argument("--delete", action="store_true", help="Actually delete files listed in logs/models_to_delete.json.")
    args = parser.parse_args()

    project_root = Path.cwd()
    roots = args.root or [project_root]
    if args.pi_defaults:
        roots.extend(
            [
                Path.home() / "Downloads",
                Path.home() / "models",
                Path.home() / "weights",
                Path.home() / "checkpoints",
                Path.home() / "hailo_models",
                Path.home() / "ultralytics",
                Path.home() / "model_zoo",
            ]
        )
    if args.include_user_caches:
        roots.extend(
            [
                Path.home() / ".cache" / "torch",
                Path.home() / ".cache" / "huggingface",
                Path.home() / ".cache" / "ultralytics",
            ]
        )
    logs = project_root / "logs"
    items = inventory(roots)
    planned = plan_deletes(items)
    write_json(logs / "model_inventory_before_cleanup.json", [asdict(item) for item in items])
    write_json(logs / "models_to_delete.json", [asdict(item) for item in planned])
    if args.quarantine:
        results = quarantine_files(planned, project_root / "model_quarantine")
    elif args.delete:
        results = delete_files(planned)
    else:
        results = [DeleteResult(item.path, False, "dry-run; pass --quarantine to move or --delete to remove") for item in planned]
    write_json(logs / "model_cleanup_result.json", [asdict(result) for result in results])
    print(f"Inventoried {len(items)} model-like files; planned {len(planned)} deletions; deleted {sum(1 for r in results if r.deleted)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
