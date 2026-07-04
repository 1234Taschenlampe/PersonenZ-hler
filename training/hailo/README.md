# Hailo-10H Compilation

Run this folder on an x86-64 Ubuntu host with a compatible Hailo Software Suite, Dataflow Compiler, Model Zoo and HailoRT version.

Target:

```text
training/hailo/artifacts/yolo26x_person_hailo10h_640.hef
```

The Raspberry Pi currently uses HailoRT 5.1.1 and HAILO10H firmware 5.1.1. Do not deploy a HEF until toolchain compatibility is documented in `docs/model_toolchain_manifest.md`.

Expected command:

```bash
python training/hailo/compile_yolo26x.py \
  --onnx training/exports/yolo26x_person_640.onnx \
  --calibration /path/to/calibration/images \
  --target hailo10h
```

This script fails early if Hailo DFC commands are not available.
