# Monitoring Reference

## GUI

Die GUI zeigt Backend-/Modellzustand, Hailo-Latenz, End-to-End-Latenz, Queue, verworfene Frames, CPU, RAM und Temperatur. Re-ID-Metriken bleiben bei der sicheren Standardkonfiguration inaktiv. Kamera-Vorschauen sind standardmaessig verdeckt.

## Status-API

Sicherer lokaler Start (Tokens aus dem EnvironmentFile erforderlich):

```bash
python scripts/status_api.py --project-root /home/raspibob/PersonenZ-hler
```

Oeffentlich sind nur:

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/privacy/notice`

`viewer` darf Status, Zaehler, Kamera-/Runtime-Zustand und WebSocket lesen. `operator` darf zusaetzlich Telemetrie, Metriken, Ereignisse und den explizit aktivierten anonymisierten Stream lesen. `admin` darf exportieren und loeschen. Alle Antworten verhindern Caching; externe Bindung benoetigt TLS.

Die API gibt keine Tokens, Embeddings, Geraetepfade oder rohe Hailo-Identifikationsausgaben aus. Datenbankmetrik enthaelt nur Vorhandensein und Groesse, keinen Pfad. Audit-Logs enthalten keine IP-Adressen oder Nutzdaten.

Weitere Details: `docs/PRIVACY_AND_SECURITY.md`.
