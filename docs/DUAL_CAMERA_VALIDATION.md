# Dual Camera Validation

Historischer Stand: 2. Juli 2026. Geraeteseriennummern und stabile Hardwarepfade wurden aus dieser versionierten Dokumentation entfernt.

## Hardware und Pipeline

- Zwei Logitech-C920-Kameras wurden mit MJPEG, 1280x720 und 15 FPS geprueft.
- `LatestFrameHub` haelt pro Kamera nur den neuesten Frame; alte Frames werden ersetzt statt aufgestaut.
- Tracker sind pro Kamera getrennt. Nur bestaetigte Tracks koennen Zaehlen ausloesen.
- Re-ID ist inzwischen im sicheren Standard deaktiviert. Bei bewusster Aktivierung bleiben Embeddings nur im RAM; vorher ist eine gesonderte Datenschutzpruefung erforderlich.

## Historische Leistungsmessung

- YOLO11x Hailo-Latenz: etwa 56-57 ms.
- Hailo-Benchmark: 22,63 FPS.
- Eine Kamera bei 15 FPS: E2E p95 etwa 63-64 ms.
- Zwei Kameras bei 15 FPS: E2E p95 etwa 125 ms; Frames werden verworfen statt gepuffert.

Die Praxisszenarien mit realen Personen und dem produktiven YOLO26m-HEF muessen auf dem Zielgeraet erneut validiert werden, ohne Testbilder oder Identifikatoren in Git/Logs zu uebernehmen.
