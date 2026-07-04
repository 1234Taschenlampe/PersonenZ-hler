# Dual Camera Validation

Datum: 2026-07-02

## Hardware

- Kamera 1: Logitech C920, `/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920-video-index0`
- Kamera 2: Logitech C920, `/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_C31BDB1F-video-index0`
- Beide Kameras wurden per Hardwaretest geöffnet und lieferten Frames.
- Startkonfiguration: MJPEG, 1280x720, 15 FPS, `CAP_PROP_BUFFERSIZE=1`.

## Pipeline

- `LatestFrameHub` verwendet genau einen aktuellen Frame-Slot pro Kamera.
- Alte Frames werden ersetzt und als Drops gezählt.
- Der gemeinsame Worker bedient Kameras fair alternierend.
- Keine wachsende Kamera-Queue.

## Messwerte mit YOLO11x

YOLO26x-HEF fehlt noch, deshalb sind die bisherigen Dual-Kamera-Latenzen mit YOLO11x gemessen.

- YOLO11x reine Hailo-Latenz: ca. 56-57 ms
- Hailo Benchmark: 22.63 FPS
- 1 Kamera, 15 FPS: E2E p95 ca. 63-64 ms, keine Drops
- 2 Kameras, 15 FPS: E2E p95 ca. 125 ms, Drops statt Rückstau

## Tracking und ReID

- Pro Kamera existiert ein eigener Tracker.
- Nur bestätigte Tracks können Zählereignisse auslösen.
- OSNet wird nicht pro Frame ausgeführt, sondern nur für bestätigte Tracks mit konfigurierbarem Intervall.
- OSNet-Embeddings bleiben nur im RAM und fließen in die globale ID-Zuordnung ein.

## Noch nicht praktisch validiert

Die geforderten Praxisszenarien mit realen Personen wurden nicht vollständig durchgeführt, weil YOLO26x-HEF noch fehlt und die produktive Detektion korrekt fail-closed bleibt.
