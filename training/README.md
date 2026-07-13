# Custom YOLO26x Person Training Pipeline

Goal: fine-tune the official YOLO26x detection checkpoint for a single `person` class using frames captured from the two real Logitech C920 cameras, then export ONNX and compile a HAILO10H HEF without replacing the working YOLO11x fallback until real tests prove parity or improvement.

Raw images, videos, labels, checkpoints, ONNX, HAR and HEF files are intentionally ignored by Git. Use an encrypted, access-restricted path outside the repository and pass it explicitly with `--output`.

```text
[encrypted training volume]
```

Required high-level phases:

1. Create a time-limited privacy approval JSON as described in `docs/PRIVACY_AND_SECURITY.md`, then capture footage with `--privacy-approval` and explicit `--output`.
2. Extract sparse frames with `training/scripts/extract_frames.py`.
3. Remove near-duplicates with `training/scripts/deduplicate_frames.py`.
4. Annotate one class only: `0 person`.
5. Validate labels with `training/scripts/validate_labels.py`.
6. Split by session/scenario, not random frame leakage, with `training/scripts/split_dataset.py`.
7. Train on an x86-64 NVIDIA GPU using `training/scripts/train_yolo26x.py`.
8. Export ONNX with `training/scripts/export_onnx.py`.
9. Verify ONNX with `training/scripts/verify_onnx.py`.
10. Compile HEF on x86-64 Hailo DFC with `training/hailo/compile_yolo26x.py`.
11. Verify HEF with `training/hailo/verify_hef.py`.
12. Transfer HEF to the Pi only after validation.

The target production HEF path on the Pi is:

```text
/home/raspibob/PersonenZ-hler/models/yolo26x_person_hailo10h_640.hef
```

The current working YOLO11x HAILO10H detector must remain available as fallback.
