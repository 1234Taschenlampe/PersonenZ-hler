# Latency Analysis and Optimization

Datum: 2026-07-02  
Zielsystem: BOB, `/home/raspibob/PersonenZ-hler`  
Branch: `feature/production-yolo26x-hailo10h`

## Kurzfazit

Die hohe End-to-End-Latenz wurde nicht durch eine wachsende CPU-Queue verursacht, sondern durch die Kombination aus serieller Hailo-Inferenz und Kameraeingangsraten, die hoeher als der YOLO11x-Durchsatz sind. Die Pipeline verwendet jetzt pro Kamera genau einen Latest-Frame-Slot. Neue Frames ersetzen alte Frames; die Inferenz arbeitet keinen Rueckstau mehr ab.

Die GUI zeigt jetzt Backend, HEF, HEF-SHA-256, Hailo-Geraet, reine Hailo-Inferenzlatenz, End-to-End-Latenz, Frame-Alter, Queue-Laenge und verworfene Frames.

## Code-Aenderungen

- `LatestFrameHub`: ein Slot pro Kamera, alte unbearbeitete Frames werden ersetzt und als Drops gezaehlt.
- Kamera-Capture setzt MJPG, Zielaufloesung/FPS und `CAP_PROP_BUFFERSIZE=1`.
- Inferenzworker verarbeitet fair alternierend den neuesten Frame beider Kameras und verwirft Frames ueber 500 ms Alter.
- Hailo-Zeitmessung trennt Resize, Letterbox, Input-Binding, Hailo-`run()`, Output-Abholung und Decode.
- End-to-End-Latenz wird ab Kameraempfang/Frame-Erstellung gemessen, nicht nur ab Pipeline-Start.
- GUI-Frame-Ausgabe ist auf 15 Updates/s je Kamera begrenzt; Diagnosewerte werden unabhaengig aktualisiert.
- `scripts/latency_benchmark.py` misst Headless-Laeufe mit YOLO11x, ohne die Produktions-Gates fuer YOLO26x zu lockern.

## HailoRT-Nachweis

`hailortcli --help` wurde zuerst verwendet. Die installierte CLI unterstuetzt unter anderem `scan`, `parse-hef`, `benchmark`, `measure-power`, `monitor` und `fw-control identify`.

Messbefunde:

- Hailo-Geraet: `[-] Device: 0001:01:00.0`
- Firmware: `5.1.1`
- Architektur: `HAILO10H`
- YOLO11x HEF: `models/yolo11x_hailo10h.hef`
- YOLO11x HEF SHA-256: `028c49694d95449bf34d1b8b320531979a96407c44be37e572a2a8e603df320c`
- `parse-hef`: kompatibel fuer `HAILO15H, HAILO10H`, Input `UINT8 NHWC(640x640x3)`, Output `HAILO NMS BY CLASS`
- `hailortcli benchmark -t 5 models/yolo11x_hailo10h.hef`: 22.63 FPS
- Benchmark-Temperatur: mean 56.69 C, min 54.11 C, max 58.06 C
- `hailortcli monitor`: ohne laufende App mit `HAILO_MONITOR=1` keine Nutzungsdateien
- `hailortcli measure-power`: Power/Current nicht unterstuetzt bzw. `HAILO_OPEN_FILE_FAILURE`

## Kameranachweis

Erkannte Kameras:

- HD Pro Webcam C920 auf `/dev/video0`
- HD Pro Webcam C920 auf `/dev/video2`

Beide C920-Kameras unterstuetzen MJPG und 1280x720 mit 15 FPS und 30 FPS. Vor der Aenderung standen die Devices im laufenden Format auf YUYV; der Capture-Code fordert nun MJPG explizit an.

## Vergleichsmessung YOLO11x

Alle Werte stammen aus `logs/latency_matrix/*.json` auf BOB. Dauer je Lauf: 12 s. GUI: aus. OSNet: aus, weil `models/osnet_x1_0_hailo10h.hef` auf BOB fehlt. Tracker: eingebetteter IoU-Fallback; Ultralytics ist installiert, ByteTrack ist noch nicht verdrahtet.

| Lauf | Kameras | Input FPS | Tracker | Hailo mean ms | E2E mean ms | E2E p95 ms | E2E max ms | Frame-Alter p95 ms | Drops | CPU mean % | RAM mean % |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|---:|---:|
| yolo11x_1cam_15fps_no_tracker | 1 | 15 | aus | 56.5 | 62.0 | 63.4 | 66.9 | 0.1 | camera_1: 0 | 6.0 | 7.0 |
| yolo11x_1cam_15fps_tracker | 1 | 15 | an | 56.7 | 63.1 | 63.9 | 66.6 | 0.2 | camera_1: 0 | 7.3 | 7.2 |
| yolo11x_1cam_30fps_no_tracker | 1 | 30 | aus | 56.6 | 78.6 | 94.1 | 97.1 | 31.7 | camera_1: 160 | 8.0 | 7.0 |
| yolo11x_1cam_30fps_tracker | 1 | 30 | an | 56.6 | 78.7 | 93.1 | 97.3 | 31.2 | camera_1: 160 | 9.7 | 7.2 |
| yolo11x_2cam_15fps_no_tracker | 2 | 15 | aus | 56.6 | 94.5 | 124.6 | 130.1 | 62.3 | camera_1: 78, camera_2: 78 | 9.2 | 7.3 |
| yolo11x_2cam_15fps_tracker | 2 | 15 | an | 56.6 | 95.0 | 125.5 | 131.2 | 63.2 | camera_1: 78, camera_2: 78 | 10.3 | 6.9 |
| yolo11x_2cam_30fps_no_tracker | 2 | 30 | aus | 56.6 | 85.9 | 118.2 | 128.9 | 57.1 | camera_1: 251, camera_2: 123 | 14.9 | 7.2 |
| yolo11x_2cam_30fps_tracker | 2 | 30 | an | 56.8 | 85.5 | 119.6 | 130.1 | 57.0 | camera_1: 252, camera_2: 123 | 12.5 | 7.2 |

## Interpretation

YOLO11x benoetigt in der Anwendung etwa 56-57 ms reine Hailo-`run()`-Zeit. Damit sind bei Batch 1 praktisch rund 17-18 Inferenzaufrufe/s erreichbar. Eine Kamera bei 15 FPS bleibt aktuell und erzeugt keine Drops. Eine Kamera bei 30 FPS und zwei Kameras bei 15/30 FPS erzeugen erwartete Drops, aber keinen wachsenden Rueckstau mehr.

Der Tracker ist in diesen Messungen nicht der Engpass. Der Unterschied zwischen Tracker an/aus liegt im Bereich von ca. 0-1 ms, weil der aktuelle Fallback-Tracker sehr leichtgewichtig ist und in der Szene keine Personen detektiert wurden.

## Nicht abgeschlossen, weil Artefakte fehlen

- YOLO26x wurde nicht gemessen: `models/yolo26x_person_hailo10h_640.hef` fehlt auf BOB.
- OSNet wurde nicht gemessen: `models/osnet_x1_0_hailo10h.hef` fehlt auf BOB.
- GUI-Messung mit Produktions-App wurde nicht ausgefuehrt, weil die Produktionskonfiguration wegen fehlender YOLO26x-Custom-HEF korrekt blockiert. Die GUI ist aber fuer die neuen Diagnosewerte instrumentiert.
- Hailo-Auslastung aus `monitor` wurde nicht numerisch erfasst, weil die installierte CLI dafuer eine laufende App mit `HAILO_MONITOR=1` braucht.

## Abnahme gegen Kriterien

- Keine wachsende Frame-Queue: erfuellt durch `LatestFrameHub`.
- Bild bleibt aktuell: erfuellt; Frame-Alter p95 bleibt sichtbar und wird gemessen.
- Reine Hailo-Latenz getrennt: erfuellt durch `hailo_inference_ms`.
- End-to-End-Latenz getrennt: erfuellt durch `end_to_end_ms`.
- Beide Kameras gleichzeitig: Headless mit zwei Kameras gemessen.
- GUI blockiert Inferenz nicht: Frame-Emission auf 15 Hz je Kamera begrenzt; GUI-Messlauf offen wegen fehlender Produktions-HEF.
- Hailo-Nutzung nachgewiesen: erfuellt durch `scan`, `identify`, `parse-hef`, Benchmark und Inferenzzaehler.
- Keine unbemerkte CPU-/Dummy-Inferenz: HailoManager laedt HEF ueber HailoRT; Benchmark-Skript meldet HailoRT-Backend und Hailo-Inferenzaufrufe.

## Empfehlung

Fuer YOLO11x ist 15 FPS pro Kamera mit zwei Kameras bereits ueber dem nachhaltigen Batch-1-Durchsatz. Die reparierte Pipeline haelt die Bilder aktuell, indem sie Frames verwirft. Wenn niedrigere Drop-Raten wichtiger sind als Eingangssampling, sollte der Eingang auf 10-15 FPS begrenzt werden. Batch 2 sollte erst getestet werden, wenn die HEF Batch 2 tatsaechlich unterstuetzt und die E2E-p95 dadurch nicht steigt.
