# Monitoring Reference

Datum: 2026-07-02

## GUI

Die GUI zeigt:

- Backend
- HEF-Datei und HEF-SHA-256
- Hailo-Gerät und Hailo-Inferenzaufrufe
- reine Hailo-Latenz
- End-to-End-Latenz und p95
- Frame-Alter
- Queue-Länge
- verworfene Frames
- OSNet-Status, OSNet-Latenz, OSNet-Aufrufe und Cache-Größe
- CPU, RAM und Temperatur

Grün darf erst angezeigt werden, wenn der jeweilige Zustand tatsächlich nachgewiesen ist. Ohne YOLO26x-HEF bleibt der aktive Detektor nicht verfügbar.

## Lokale Status-API

Start:

```bash
python scripts/status_api.py --project-root /home/raspibob/PersonenZ-hler --host 0.0.0.0 --port 8765
```

Endpunkte:

- `GET /health`
- `GET /status`
- `GET /metrics`
- `GET /api/v1/health`
- `GET /api/v1/status`
- `GET /api/v1/version`
- `GET /api/v1/counts/current`
- `GET /api/v1/telemetry/current`
- `GET /api/v1/cameras`
- `GET /api/v1/events`

Nachgewiesener Status am 2026-07-02:

- Hailo erkannt: ja
- Architektur: HAILO10H
- OSNet ready: ja
- YOLO26x-HEF vorhanden: nein
- Fallback aktiviert: nein

Die API gibt keine Bilder, Embeddings, Passwörter, Tokens oder personenbezogenen Daten aus.

## Systemmetriken

Die API meldet aktuell:

- CPU %
- RAM %
- Swap %
- freien Speicher
- Load Average
- CPU-Temperatur
- SQLite-Dateigröße und WAL-Größe
- Hailo `scan` und `fw-control identify`
