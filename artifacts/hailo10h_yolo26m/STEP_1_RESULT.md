# STEP 1 Result - YOLO26m Hailo-10H Deployment Check

Date: 2026-07-04

## Local Safety Baseline

- Source path: `C:\Users\Felix\OneDrive\Documents\Ki kammera pi`
- Backup path: `C:\Users\Felix\OneDrive\Documents\Ki_kammera_pi_backup_20260704_150446`
- Backup result: exists, 118 files copied, `robocopy` return code `1` (files copied, no copy error)
- Baseline branch: `fix/deploy-yolo26m-hailo10h`
- Baseline commit: `81ae8a2 chore: preserve local baseline before Hailo deployment`
- Remote configuration: no Git remote configured locally
- Reason almost everything was untracked: repository had no commits before the baseline commit
- Secret scan: no private keys or literal passwords found; helper scripts reference `PI_PASS` as an environment variable only

## Pi Environment

- SSH target: `bob`
- Hostname: `BOB`
- User: `raspibob`
- OS: Debian GNU/Linux 13 (trixie)
- Kernel: `Linux BOB 6.18.34+rpt-rpi-2712 ... aarch64`
- Architecture: `aarch64`
- Hailo PCIe device: `0001:01:00.0 ... Hailo-10H AI Processor [1e60:45c4]`
- HailoRT CLI: `5.1.1`
- Firmware: `5.1.1 (release,app)`
- Device architecture: `HAILO10H`
- Hailo packages: `h10-hailort 5.1.1`, `h10-hailort-pcie-driver 5.1.1`, `hailo-tappas-core 5.1.0`, `python3-h10-hailort 5.1.1-1`
- Full capture: `artifacts/hailo10h_yolo26m/pi_environment.txt`

## Official Hailo Apps Repository

- Path: `/home/raspibob/hailo-apps`
- Remote: `https://github.com/hailo-ai/hailo-apps.git`
- Current commit: `891ce70 Release/26.03.1 (#149)`
- Latest fetched tag observed: `26.03.1`
- Initial local state: detached HEAD, existing local modification in `yolo26/pose_estimation/pose_estimation_onnx_postproc.py`
- New local compatibility fix applied: `yolo26/object_detection/object_detection_onnx_postproc.py` import corrected to the existing YOLO26 object-detection utils module
- Backup of patched official file: `hailo_apps/python/standalone_apps/yolo26/object_detection/object_detection_onnx_postproc.py.codex_backup_20260704_151010`

## Installer and Runtime Setup

- `sudo -n` is not available: `sudo: a password is required`
- Official `./install.sh --no-tappas-required --dry-run` could not run under sudo for the same reason
- Created local venv: `/home/raspibob/hailo-apps/venv_hailo_apps`
- Installed runtime deps in that venv: `lap`, `cython_bbox`, `onnxruntime`, `python-dotenv`
- Verified imports: `hailo_platform`, `lap`, `cython_bbox`, `onnxruntime`, `cv2`, `numpy`, `yaml`

## YOLO26 Object Detection Result

Found script:

```text
/home/raspibob/hailo-apps/hailo_apps/python/standalone_apps/yolo26/object_detection/object_detection_onnx_postproc.py
```

Help works after the local import fix. The official resources catalog does not provide Hailo-10H object-detection YOLO26 models:

```text
Available models for: object_detection_onnx_postproc (hailo10h) [standalone]
Architecture 'hailo10h' not supported. Available: hailo8, hailo8l
```

Executed official commands:

```bash
python3 object_detection_onnx_postproc.py -n yolo26m -i bus --no-display --save-output --show-fps
python3 object_detection_onnx_postproc.py -n yolo26s -i bus --no-display --save-output --show-fps
python3 object_detection_onnx_postproc.py -n yolo26n -i bus --no-display --save-output --show-fps
```

All failed before inference:

```text
Model 'yolo26m' not found and not in available models list. Available models for object_detection_onnx_postproc/hailo10h (standalone): None
Model 'yolo26s' not found and not in available models list. Available models for object_detection_onnx_postproc/hailo10h (standalone): None
Model 'yolo26n' not found and not in available models list. Available models for object_detection_onnx_postproc/hailo10h (standalone): None
```

Conclusion: official YOLO26 object detection for Hailo-10H is not available in this installed/fetched `hailo-apps` release. Per instruction, the own project pipeline was not changed because the required official object-detection proof does not exist yet.

## YOLO26m Pose Validation

Hailo Apps does provide YOLO26 pose models for Hailo-10H:

```text
pose_estimation_onnx_postproc/hailo10h:
default: yolo26m_pose
extra: yolo26s_pose, yolo26n_pose
```

Readable project copies:

```text
/home/raspibob/PersonenZ-hler/models/yolo26m_pose_hailo10h_640.hef
/home/raspibob/PersonenZ-hler/models/yolo26m_pose_postprocessing.onnx
/home/raspibob/PersonenZ-hler/models/config_onnx_yolo26m_pose.json
```

SHA-256:

```text
9dbb28a3c1b89e1467eef58042402b56620ecd4b771b01cfaf10d0687154bbae  yolo26m_pose_hailo10h_640.hef
1eaa064b77ad1be1900be0f43501f6e49536ba962a76f2285f0f78e8a4a9ce46  yolo26m_pose_postprocessing.onnx
24a1a2aae8c615625d7bb64d3e609ff8f268f2924a71e1914de1d8db791e8977  config_onnx_yolo26m_pose.json
```

`hailortcli parse-hef` summary:

```text
HEF Compatible for: HAILO15H, HAILO10H
Network group name: yolo26m_pose, Multi Context - Number of contexts: 5
Input yolo26m_pose/input_layer1 UINT8, NHWC(640x640x3)
Outputs: conv73, conv92, conv109, conv74, conv93, conv110, conv77, conv96, conv113
```

Benchmark after temporarily freeing `/dev/hailo0`:

```text
yolo26m_pose: FPS: 48.37
temperature: mean=67.59 min=66.10 max=68.27
```

Official pose image test:

```bash
python3 pose_estimation_onnx_postproc.py \
  -n /home/raspibob/PersonenZ-hler/models/yolo26m_pose_hailo10h_640.hef \
  -i /home/raspibob/PersonenZ-hler/logs/camera_test/person_test_zidane.jpg \
  --onnx /home/raspibob/PersonenZ-hler/models/yolo26m_pose_postprocessing.onnx \
  --onnx-config /home/raspibob/PersonenZ-hler/models/config_onnx_yolo26m_pose.json \
  --no-display --save-output --show-fps
```

Result:

```text
Processed 1 frames at 3.73 FPS, Total time: 0.27 seconds
Processing completed successfully.
Output: /home/raspibob/hailo-apps/codex_outputs/yolo26_pose_person_test_explicit/output_0.png
```

Automatic pose resolution found root-owned files under `/usr/local/hailo/resources`, but they are not readable by `raspibob` (`system error number 13`). Explicit readable paths were required.

Official pose camera test:

```bash
python3 pose_estimation_onnx_postproc.py \
  -n /home/raspibob/PersonenZ-hler/models/yolo26m_pose_hailo10h_640.hef \
  -i /dev/video0 \
  --onnx /home/raspibob/PersonenZ-hler/models/yolo26m_pose_postprocessing.onnx \
  --onnx-config /home/raspibob/PersonenZ-hler/models/config_onnx_yolo26m_pose.json \
  --no-display --show-fps --time-to-run 60
```

Result: did not complete successfully. It entered camera processing mode but produced no FPS/output before it was killed after exceeding the expected runtime. Exit was `143`. No output file was created.

## Camera Devices

```text
HD Pro Webcam C920 (usb-xhci-hcd.1-1): /dev/video0, /dev/video1
HD Pro Webcam C920 (usb-xhci-hcd.0-1): /dev/video2, /dev/video3
```

## Visitor Counter Service State

- Before tests: `visitor-counter.service` active, PID held `/dev/hailo0`, running YOLO11x HEF.
- `systemctl stop` and `systemctl reset-failed/start` require interactive authentication.
- During testing, the service hit systemd start-limit due repeated temporary process kills.
- Restored runtime manually as user `raspibob`:

```text
manual_pid=3751
/dev/hailo0 held by python PID 3751
YOLO11x Detection HAILO10H - Hailo-Inferenz aktiv
```

The systemd unit remains `failed` until someone with sudo runs:

```bash
sudo systemctl reset-failed visitor-counter.service
sudo systemctl start visitor-counter.service
```

## Changed Local Files

- Added `.gitignore`
- Added local audit artifacts under `artifacts/hailo10h_yolo26m/`
- Created baseline commit `81ae8a2`

## Local Test Results

Targeted tests:

```text
pytest tests/unit/test_latency_pipeline.py tests/unit/test_configuration.py
7 passed in 0.42s
```

Full test suite:

```text
$env:PYTHONPATH = "${PWD};${PWD}\src"; pytest
40 passed, 4 skipped, 8 deselected in 1.80s
```

Plain `pytest` without `PYTHONPATH` failed during collection because `tests/unit/test_status_api.py` imports `scripts.status_api` and the repository root was not on `PYTHONPATH`.

## Current Blockers

1. Official YOLO26 object detection for Hailo-10H is not present in `hailo-apps` tag `26.03.1`; `yolo26m`, `yolo26s`, and `yolo26n` all fail model resolution for `object_detection_onnx_postproc/hailo10h`.
2. Installed HailoRT is `5.1.1`; the requested ideal official YOLO26 flow mentions `5.3.0`. Packages were not upgraded blindly.
3. Root-owned official resources in `/usr/local/hailo/resources` are not readable by `raspibob`.
4. Service management requires interactive authentication; systemd service is failed but the app was manually restarted as user.
5. Official camera test for YOLO26m-pose did not complete; it hung in camera processing and was killed.

## Next Technical Step

Obtain or enable an official Hailo-10H YOLO26 object-detection resource for `object_detection_onnx_postproc`, or install the Hailo 5.3.0-compatible resource set with sudo access. Only after the official object-detection image test succeeds should `src/visitor_counter/hailo_manager.py` be changed to integrate YOLO26 object-detection HEF plus ONNX postprocessing.
