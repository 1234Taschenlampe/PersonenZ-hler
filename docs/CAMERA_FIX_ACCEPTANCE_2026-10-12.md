# Abnahme nach Kamera-/Zählerkorrekturen (12.10.2026)

## Was dieser Branch behebt

- Die isolierten Parallel-Inferenz-Tests initialisieren ihren Zustand korrekt und lassen die Produktionssperren unverändert.
- Bildrand-Disappearance und Track-Ablauf verwenden echte **verarbeitete Kamera-Frames** statt Frame-ID-Differenzen des RTSP-Eingangs. Der LatestFrameHub darf Frames zur Latenzbegrenzung verwerfen.
- Die authentifizierte `GET /api/v1/readiness`-API unterscheidet KI-Bereitschaft von `GET /health` (reine API-Liveness). Ein einzelner aktiver Kamerafeed ist `degraded`, nicht vollständiger Ausfall.
- `counts.last_event_time` beschreibt das letzte **bestätigte** IN/OUT-Ereignis seit Prozessstart, nicht mehr die letzte beliebige Erkennung. Der Wert ist derzeit kein über Neustarts persistierter Zeitstempel.
- Die globale Inferenzlatenz benutzt den tatsächlich eingesetzten Hailo-Kontext statt pauschal den primären.

## Vor einem Merge auf dem Raspberry Pi BOB

1. Die vollständige GitHub-CI des **letzten Commits** muss grün sein; ein älterer grüner Lauf reicht nicht.
2. Laufende Produktionskonfiguration, Secrets, Datenbanken und Dienste sichern. Kein automatisches Upgrade während einer Vorführung.
3. Beide Reolink-RTSP-Hauptstreams authentifiziert öffnen; pro Kamera laufende gültige Frames und `ai_fps > 0` prüfen. 20+ Kamera-FPS allein beweisen keine KI-Verarbeitung.
4. Für beide Kameras mindestens 10 kontrollierte Eintritte und Austritte in der jeweiligen Richtung ausführen. Statisches Stehen, Umkehren vor dem Rand, Verdeckung in Bildmitte und zwei gleichzeitig durchlaufende Personen ebenfalls prüfen. Erwartete und tatsächliche Zähler protokollieren, ohne Bilder zu speichern.
5. Frame-Lücken / langsame Inferenz: Bildrandereignisse dürfen nicht allein durch große Capture-Frame-ID-Sprünge ausgelöst werden. Gleichzeitig dürfen echte bestätigte Passagen nicht verlorengehen.
6. Bei absichtlichem Ausfall von Kamera 2 soll Kamera 1 weiter zählen, `/api/v1/readiness` mit gültigem Viewer-Token `200 degraded` zurückgeben. Wenn beide KI-Auswertungen ausfallen, muss der Endpoint `503 unavailable` liefern, während `/health` weiterhin die API-Liveness bestätigt.
7. Einen echten Reconnect, Restart, SQLite-Persistenz und Warnmeldungen auf einem Android-Gerät testen.
8. Einen überwachten Dauertest durchführen; CPU/RAM, Temperatur, Latenz-p95, KI-FPS je Kamera und falsche Ein-/Austritte prüfen.

## Weiterer offener Punkt

Die Konfiguration nennt derzeit `bytetrack`, aber `src/visitor_counter/tracker.py` verwendet `IoUFallbackTracker` (auch bei installiertem Ultralytics). Das ist **kein** vollständiger ByteTrack. Ein echter Tracking-Umbau benötigt getrennte Praxistests mit schnell bewegten und sich verdeckenden Personen. Er ist bewusst **nicht** ungeprüft in diesen stabilisierenden Fix gemischt worden.

Zusätzlich bleiben Echtgeräte-Prüfung von OSNet-Deduplizierung, Modelltreffsicherheit unter realem Licht und die Langzeitstabilität offen. Automatische CI-Tests simulieren diese Punkte nicht.
