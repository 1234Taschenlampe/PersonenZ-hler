# YOLO26m Detection Hailo10H Ready

Date: 2026-07-04
Branch: fix/deploy-yolo26m-hailo10h

## Result

YOLO26m object detection is installed and running on the Raspberry Pi Hailo10H path. It is a COCO object-detection model with person filtering in the visitor counter runtime. The previous pose-only YOLO26m HEF is no longer used as the detector, and YOLO11x is no longer the active runtime model.

Final live process:

- PID: 5663
- Holds `/dev/video0`, `/dev/video2`, and `/dev/hailo0`
- Configured HEF: `models/yolo26m_detection_hailo10h_640.hef`
- HEF SHA256: `f1435f7235c77b05736a5ab01b673cc156a95d85b5126aee7f7eb062ec2b2c66`
- Postprocess ONNX SHA256: `2401071729d3d5e59145920aefe66afae0443731de2546d3239dbec3bb2a6e2f`
- Runtime status: `YOLO26m COCO Detection HAILO10H (person filter) - Hailo-Inferenz aktiv`

## Why YOLO26m, Not YOLO26x

Hailo Model Zoo v5.4.0 lists YOLO26 object detection HEFs for Hailo10H for `yolo26m`, `yolo26s`, and `yolo26n`. It does not list a Hailo10H `yolo26x` object-detection HEF. Therefore the strongest available official Hailo10H YOLO26 detector is `yolo26m`.

Source HEF:

- `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.4.0/hailo10h/yolo26m.hef`

Source ONNX package:

- `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ObjectDetection/Detection-COCO/yolo/yolo26m/2026-02-16/yolo26m.zip`

## Installed Pi Files

- `/home/raspibob/PersonenZ-hler/models/yolo26m_detection_hailo10h_640.hef`
- `/home/raspibob/PersonenZ-hler/models/yolo26m_postprocessing.onnx`
- `/home/raspibob/PersonenZ-hler/models/config_onnx_yolo26m.json`

## Code Changes

- `src/visitor_counter/hailo_manager.py`
  - Added YOLO26 detection ONNX postprocess loading.
  - Maps six Hailo output tensors into ONNXRuntime inputs.
  - Parses `(300, 6)` YOLO26 postprocess output and filters COCO class `0` person.

- `src/visitor_counter/configuration.py`
  - Default detector target changed to `models/yolo26m_detection_hailo10h_640.hef`.
  - Added required postprocess ONNX/config paths.
  - Keeps fallback disabled and pose HEF forbidden.

- `config/config.yaml`
  - Runtime now targets YOLO26m Detection Hailo10H.

- `src/visitor_counter/model_manager.py`
  - Reports approved YOLO26 detector readiness instead of hard-coded missing YOLO26x.

- `src/visitor_counter/gui.py`
  - HEF selection and status text now use the configured YOLO26m target.

- `src/visitor_counter/types.py`
  - Default detection model label updated to YOLO26m.

## Verification

HailoRT parse:

- `HEF Compatible for: HAILO15H, HAILO10H`
- Input: `UINT8 NHWC(640x640x3)`
- Outputs:
  - `yolo26m/conv71`
  - `yolo26m/conv87`
  - `yolo26m/conv101`
  - `yolo26m/conv74`
  - `yolo26m/conv90`
  - `yolo26m/conv104`

Static Hailo image smoke:

- `person_test_zidane.jpg`: 2 person detections
- `camera_1_direct_raw.jpg`: 1 person detection
- `camera_2_direct_raw.jpg`: 0 person detections
- Typical Hailo inference: about 39-41 ms
- Typical total Hailo + postprocess call: about 50-66 ms

Live GUI/runtime:

- `Display raw frames only mode: False`
- `Loaded yolo26_detection ONNX postprocess`
- `YOLO26m COCO Detection HAILO10H (person filter) - Hailo-Inferenz aktiv`
- `GUI_RENDER ... source=raw`
- `GUI_RENDER ... source=processed`
- Both cameras remain visible.

Tests:

- Local full suite: `42 passed, 4 skipped, 8 deselected`
- Pi hardware suite with `-m hardware`: `8 passed`

## Artifacts

- `artifacts/yolo26m_detection_hailo10h/yolo26m_detection_parse_hef.txt`
- `artifacts/yolo26m_detection_hailo10h/yolo26m_detection_hailo_smoke.json`
- `artifacts/yolo26m_detection_hailo10h/yolo26m_ready_20260704_1606.log`
- `artifacts/yolo26m_detection_hailo10h/yolo26m_ready_desktop.png`

## Operational Note

The verified ready state is the manually launched visible GUI process with:

```bash
DISPLAY=:0
XDG_RUNTIME_DIR=/run/user/1000
QT_QPA_PLATFORM=xcb
```

The earlier systemd unit issue remains separate: the installed service unit had `QT_QPA_PLATFORM=offscreen` and systemd required sudo/auth to reset the failed start-limit state.
