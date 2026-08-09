# PersonenZähler V2

Lokaler Dual-Kamera-Personenzähler für Raspberry Pi 5 + Hailo-10H. Ziel ist eine robuste Ein-/Ausgangszählung mit möglichst wenig dauerhaft gespeicherten personenbezogenen Daten.

## Zielarchitektur

```text
WLAN-Kamera 1 ─┐
                ├─ eigener Router ─ Raspberry Pi 5 + Hailo-10H
WLAN-Kamera 2 ─┘                         │
                                        ├─ YOLO26m Person Detection
                                        ├─ lokales Tracking
                                        ├─ OSNet ReID
                                        ├─ temporäre globale Person-ID
                                        ├─ A/neutral/B-Zonenlogik
                                        ├─ Dual-Camera-Consensus
                                        ├─ SQLite / lokale API
                                        └─ zwei lokale Displays
```

Die Kameras können RTSP/RTSPS/HTTP/HTTPS liefern; USB/V4L2 bleibt für Entwicklung und Tests unterstützt. Der Pi sollte am eigenen Router nach Möglichkeit per Ethernet hängen.

## Zähllogik

YOLO26m erkennt nur Personen. Lokales Tracking hält Bewegungsverläufe innerhalb einer Kamera stabil. OSNet erzeugt temporäre Merkmalsvektoren zur kameraübergreifenden Wiedererkennung. Eine interne `global_person_id` verbindet lokale Tracks derselben unbekannten Person; sie wird nicht mit Namen oder realen Identitäten verknüpft. Eine Zählung entsteht erst durch die deterministische Passage-Logik aus Zonenfolge, Richtung, Zeitfenster und Consensus. ReID allein darf keine Person zählen.

`inside`, `entered` und `exited` werden in der Produktionspipeline nur durch bestätigte Crossing-/Consensus-Ereignisse verändert. Sichtbarkeit ist davon getrennte Telemetrie.

## Datenschutzstandard

- Verarbeitung lokal auf Pi/Hailo
- keine Cloud-Telemetrie für Kameradaten
- temporäre pseudonyme Person-ID bleibt für Matching erhalten
- OSNet ReID bleibt für Cross-Camera-Matching aktiv
- keine Gesichtserkennung und keine Namenszuordnung
- keine Alters-, Geschlechts-, Emotions- oder Herkunftsklassifizierung
- keine dauerhafte Speicherung von Video oder Einzelbildern
- ReID-Embeddings nur temporär im RAM
- granulare Ereignisspeicherung standardmäßig aus
- Remote-API nur mit Authentifizierung; außerhalb Loopback zusätzlich TLS
- Kamerabetrieb wird blockiert, solange Betreiber-, Zweck- und Datenschutzhinweis-Felder nicht ausgefüllt sind

Lokale Verarbeitung bedeutet nicht automatisch DSGVO-Konformität. Der konkrete Standort und Einsatzzweck müssen separat geprüft werden. Siehe [Datenschutzprüfung Deutschland 2026](docs/PRIVACY_GERMANY_2026.md) und [Datenschutz- und Sicherheitskonzept](docs/PRIVACY_AND_SECURITY.md).

## Lizenz- und Startschutz

Der normale GUI- und Service-Start ist für die Produktivkonfiguration fail-closed geschützt. Die Anwendung prüft eine lokal signierte Lizenz und standardmäßig eine dazu passende signierte Freischaltung auf GitHub. Die Prüfung nutzt HTTPS und Ed25519-Signaturen; der private Signierschlüssel gehört nicht auf den Raspberry Pi oder ins Repository. Der Emulator bleibt davon getrennt, damit Entwicklung und CI möglich sind.

Details: [Lizenz- und Entitlement-System](docs/LICENSE_SYSTEM.md).

## Digital Twin

Der Hardware-freie Emulator verwendet die echte Tracking-, Identity-, Zonen- und Consensus-Logik, ersetzt aber Kamera, YOLO/Hailo und OSNet durch deterministische synthetische Daten.

```bash
PYTHONPATH=src python -m visitor_counter.emulator
```

Grafisch:

```bash
PYTHONPATH=src python -m visitor_counter.emulator_gui
```

Details: [Digital-Twin-Emulator](docs/EMULATOR.md).

## Lokaler KI-Assistent

Ein lokaler Projektassistent ist vorbereitet. Standardmodell ist Gemma 4 E2B Instruct über einen ausschließlich auf Loopback erreichbaren `llama.cpp`-Server. Er durchsucht freigegebene Projektdateien lokal, erklärt das System und kann kleine Änderungen vorschlagen. Änderungen werden nie autonom angewendet, sondern benötigen eine explizite Bestätigung und passieren eine deterministische Sicherheitsprüfung.

Details: [Lokaler Projektassistent](docs/LOCAL_AGENT.md).

## Tests und CI

```bash
pytest
PYTHONPATH=src python -m visitor_counter.emulator
```

GitHub Actions führt Unit-Tests, Digital-Twin-Abnahmetests, Python-Compile-Checks, Bandit-Audit, Dependency-Audit und Secret-Pattern-Prüfung aus. Hardwaretests bleiben separat markiert:

```bash
pytest -m hardware
```

## WLAN-Konfiguration

`config/config.wlan.example.yaml` enthält eine Vorlage ohne echte Zugangsdaten. Reale RTSP-Benutzer, Passwörter und URLs gehören nicht ins Repository.

## Dokumentation

- [Architektur V2](docs/ARCHITECTURE_V2.md)
- [Digital Twin](docs/EMULATOR.md)
- [Datenschutz Deutschland 2026](docs/PRIVACY_GERMANY_2026.md)
- [Datenschutz und Sicherheit](docs/PRIVACY_AND_SECURITY.md)
- [Lizenzsystem](docs/LICENSE_SYSTEM.md)
- [Lokaler Gemma-Assistent](docs/LOCAL_AGENT.md)
- [Jugend-forscht-Projektdokumentation](docs/JUGEND_FORSCHT_PROJECT.md)

## Status

Die V2-Änderungen liegen bewusst in einem Draft-PR. Logik und Software können über CI und Emulator getestet werden. Aussagen zu realer Erkennungsgenauigkeit, Hailo-Leistung, thermischem Verhalten und WLAN-Stabilität werden erst nach Messungen auf der Zielhardware getroffen.
