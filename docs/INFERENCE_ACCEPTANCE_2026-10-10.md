# Detection and counting verification, 2026-10-10

## Changes

- Preserve deployed camera controls, independent single-camera startup and detector/ReID switches while integrating the latest main-stream and RGB fixes.
- Interpret native Hailo outputs as HWC explicitly. The 80x80x80 classification tensor is ambiguous by shape; its person/spatial axes must be transposed for ONNX.
- Keep tentative tracking observations for line crossing confirmation; count return passages of the same track; use actual observations rather than skipped capture IDs for stability.
- Do not suppress distinct known identities as duplicate passages.
- Use one existing capture per camera and bounded latest-frame buffers for desktop preview. Expanded JPEGs retain native dimensions; no upscaling or second desktop RTSP connection.
- Preserve configured preview consent/anonymization and remote video policy. Full-frame anonymization intentionally remains pixelated.
- Publish real received/successfully inferred frames, per-camera AI FPS, detections/confidence/tracks, inference state/latency, ReID state and rejected count/consensus reasons. Hardware telemetry uses real system sensors.

## Verified

- Windows non-hardware suite: 201 passed, 6 skipped, 8 hardware tests deselected. Skips include platform-specific symlink behavior and unavailable optional assets.
- Deployed Pi non-hardware suite: 206 passed, 1 skipped, 8 hardware tests deselected. Separate hardware presence suite: 8 passed; presence tests alone do not certify camera streams or counting.
- Deployed source updated by fast-forward; counter and status API services both active, status file refreshing within one second, Hailo and OSNet initialized without a reported detector error. Configuration SHA-256 unchanged across deployment, local license key retained and SQLite backups made using the backup API.
- Real Raspberry Pi 5 / Hailo-10H, firmware 5.1.1: patched detector run on the public Ultralytics bus test image, not a private camera frame.
- Decoded public fixture: 810x1080; model input: UINT8 RGB, 1x640x640x3. Actual output includes HWC 80x80x80 classification tensor.
- All three runs detected four people, confidences 0.7558–0.9351. Hailo execution 39.2–40.6 ms; total inference plus preprocessing/ONNX 51.9–61.5 ms. Boxes remained within native image bounds.
- Real OSNet inference: 512 dimensions, norm approximately 1.0, 7.3 ms, zero reported errors. No embeddings or frames exported.
- Automated tests cover standing persons with no entry, both crossing directions, return of the same track, delayed confirmation, skipped capture frames and single-camera operation. These are software tests, not physical passages.

## Still requires camera acceptance

Both configured main-stream paths remain unchanged. At inspection time the camera RTSP ports were unreachable from the Pi. Camera 1 answered ping; camera 2 did not. The running capture pipeline therefore received zero live frames. Configured 2560x1920 is not proof of a currently decoded resolution; actual live resolution, capture/AI FPS and person detection remain unverified until connectivity returns.

No physical standing-person or IN/OUT passage acceptance is claimed. The LAN configuration, camera addresses/credentials, database and privacy settings are preserved. Product settings and local modifications were backed up before attempting the update.

## Repeatable hardware check

With a local public/nonprivate image and exclusive access to the accelerator:

```sh
PYTHONPATH=src .venv/bin/python scripts/verify_hailo_detection.py \
  --config /path/to/local/config.yaml --image /path/to/public-test.jpg \
  --require-person --reid
```

This emits scalar/tensor metadata only and neither opens cameras nor writes the production database. Passing it does not certify camera connectivity or physical counting.
