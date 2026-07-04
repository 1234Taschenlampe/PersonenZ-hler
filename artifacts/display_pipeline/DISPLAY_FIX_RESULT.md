# Display Pipeline Fix Result

Date: 2026-07-04
Branch: fix/deploy-yolo26m-hailo10h
Fix commit: edb1fc1cfc9955dd33185c9389bc8c6e56834924

## Result

Both camera image streams can now be displayed in parallel without requiring YOLO/Hailo inference to be running. The GUI receives raw frames directly from the capture threads and can render them with a diagnostic overlay. With YOLO11x/Hailo enabled, the same raw path stays active and processed frames are rendered when inference succeeds.

Final Pi runtime check:

- Single app instance running: PID 4799
- Device ownership: PID 4799 holds `/dev/video0`, `/dev/video2`, and `/dev/hailo0`
- Display mode in final runtime: `display_raw_frames_only: false`
- Hailo status: `YOLO11x Detection HAILO10H - Hailo-Inferenz aktiv`
- Last verified log chain: `CAMERA_CAPTURE` -> `FRAME_PUBLISH` -> `GUI_RECEIVE` -> `GUI_RENDER`

## Root Cause

The original display path was coupled to the inference pipeline. Camera frames were captured into the frame hub, but the GUI only got images from `ProcessingPipeline.frame_callback`. If model loading, Hailo startup, or inference failed, the display path could receive no frame and both panes stayed blank.

A second operational issue was found on the Pi: the installed systemd unit at `/etc/systemd/system/visitor-counter.service` contains `QT_QPA_PLATFORM=offscreen`, so a service start through that unit cannot show the local HDMI GUI. The repository service files are not changed to offscreen, so the installed unit has drift and should be corrected with sudo before systemd is used for visible display.

## Changed Files And Functions

- `src/visitor_counter/camera_manager.py`
  - Added optional `FramePacketCallback` to `CameraCapture`.
  - `CameraCapture._capture_loop()` now fans out each captured packet to the frame hub and the raw display callback.
  - Added diagnostic logs every 30 frames: `CAMERA_CAPTURE`, `FRAME_PUBLISH`.
  - Callback failures are logged as `FRAME_CALLBACK_FAILED` without killing camera capture.

- `src/visitor_counter/gui.py`
  - `MainWindow.start_processing()` now starts capture threads independently from `ProcessingPipeline`.
  - Added `raw_frame_ready` signal and raw-frame render path.
  - Added `display_raw_frames_only` mode to run cameras and GUI without YOLO.
  - Added raw overlay with camera id, frame id, timestamp, and resolution.
  - Added GUI diagnostics: `GUI_RECEIVE`, `GUI_RENDER`, `GUI_RENDER_FAILED`.
  - Hardened `CameraView.set_frame()` for empty frames, invalid shapes, non-uint8 frames, non-contiguous arrays, BGR, and BGRA.

- `src/visitor_counter/inference_pipeline.py`
  - A detector/model startup failure no longer sets the shared `stop_event`.
  - This prevents inference startup failures from stopping camera capture and raw display.

- `src/visitor_counter/configuration.py`
  - Added `DisplayConfig`.

- `config/config.yaml`
  - Added:
    - `display.display_raw_frames_only: false`
    - `display.raw_frame_overlay: true`

- `config/config.example.yaml`
  - Added the same display config keys.

- `tests/unit/test_latency_pipeline.py`
  - Added coverage that `CameraCapture` publishes the same frame packet to both `LatestFrameHub` and the raw callback.

## Pi Verification

Raw-display-only test:

- Remote config was set to:
  - `display_raw_frames_only: true`
  - `raw_frame_overlay: true`
- Started manually with:
  - `DISPLAY=:0`
  - `XDG_RUNTIME_DIR=/run/user/1000`
  - `QT_QPA_PLATFORM=xcb`
- Evidence:
  - `Display raw frames only mode: True`
  - `CAMERA_CAPTURE camera=camera_1 frame=30 shape=1280x720`
  - `FRAME_PUBLISH camera=camera_1 frame=30`
  - `GUI_RECEIVE camera=camera_1 frame=30`
  - `GUI_RENDER camera=camera_1 frame=30 source=raw`
  - Same chain observed for `camera_2`

YOLO/Hailo active test:

- Remote config was set back to:
  - `display_raw_frames_only: false`
  - `raw_frame_overlay: true`
- Evidence:
  - `Starting processing pipeline`
  - `Display raw frames only mode: False`
  - `YOLO11x Detection HAILO10H - Hailo-Inferenz aktiv`
  - `/dev/video0`, `/dev/video2`, and `/dev/hailo0` held by the single app process
  - `GUI_RENDER ... source=raw`
  - `GUI_RENDER ... source=processed`
  - No `GUI_RENDER_FAILED` in the final check output

## Local Tests

- `PYTHONPATH="$PWD;$PWD/src" pytest tests/unit/test_latency_pipeline.py tests/unit/test_configuration.py`
  - 8 passed
- `PYTHONPATH="$PWD;$PWD/src" pytest`
  - 41 passed, 4 skipped, 8 deselected

## Artifacts

- `artifacts/display_pipeline/display_pipeline_raw_desktop.png`
  - Pi desktop screenshot with raw diagnostic overlays for both cameras.
- `artifacts/display_pipeline/display_pipeline_yolo_desktop.png`
  - Pi desktop screenshot with YOLO/Hailo active, detection overlay visible, and both panes present.
- `artifacts/display_pipeline/camera_1_direct_raw.jpg`
  - Direct OpenCV test frame from camera 1.
- `artifacts/display_pipeline/camera_2_direct_raw.jpg`
  - Direct OpenCV test frame from camera 2.

## Remaining Operational Note

`visitor-counter.service` is still failed from the prior systemd start-limit state and requires sudo or an interactive auth session to reset/start. Before using systemd for the visible GUI, update the installed unit to remove `QT_QPA_PLATFORM=offscreen`, then run:

```bash
sudo systemctl reset-failed visitor-counter.service
sudo systemctl daemon-reload
sudo systemctl start visitor-counter.service
```

Until that is done, the verified visible runtime is the manually started Pi process with `DISPLAY=:0`, `XDG_RUNTIME_DIR=/run/user/1000`, and `QT_QPA_PLATFORM=xcb`.
