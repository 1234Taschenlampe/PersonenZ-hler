# PersonenZähler V2

Lokaler Dual-Kamera-Personenzähler für Raspberry Pi 5 + Hailo-10H. Ziel ist eine robuste Ein-/Ausgangszählung mit möglichst wenig dauerhaft gespeicherten personenbezogenen Daten.

Das Laufzeitsystem verwendet das YOLO26m COCO Detection HEF fuer Hailo-10H und filtert auf COCO-Klasse `person`. Es soll keine CPU-Inferenz, OpenCV-DNN, Dummy-Daten oder Pose-HEFs als Ersatz fuer die produktive Detektion verwenden.

## Privacy & GDPR

Das Projekt ist auf **lokale Verarbeitung und datenschutzfreundliche Voreinstellungen** ausgelegt. Im sicheren Standardbetrieb werden Kamerabilder nur fuer die laufende Personenerkennung verarbeitet und nicht dauerhaft als Video oder Einzelbild gespeichert. Gesichtserkennung und die Speicherung dauerhafter biometrischer Gesichtsdaten sind nicht vorgesehen. Granulare Personenereignisse sind standardmaessig deaktiviert; aktiviert der Betreiber sie bewusst, verlangt das System einen externen Verschluesselungsschluessel und verwendet Pseudonymisierung sowie eine begrenzte Aufbewahrungsdauer.

Weitere Schutzmechanismen umfassen standardmaessig deaktivierte Live-/Remote-Videostreams, lokale API-Bindung an `127.0.0.1`, rollenbasierte API-Tokens, kurze Datenaufbewahrung und technische Sperren vor dem Kamerastart, solange die erforderlichen Betreiberangaben nicht dokumentiert sind.

**Wichtig:** Diese technischen Massnahmen machen einen konkreten Einsatz nicht automatisch DSGVO-konform. Der Betreiber muss insbesondere Zweck, Rechtsgrundlage, Erfassungsbereich, Transparenzinformation, Speicherdauer, Zugriffsrechte und gegebenenfalls die Erforderlichkeit einer Datenschutz-Folgenabschaetzung fuer den jeweiligen Einsatz pruefen.

Dokumentation:

- [DSGVO-Dokumentation](docs/DSGVO_DOKUMENTATION.md)
- [Datenschutz- und Sicherheitskonzept](docs/PRIVACY_AND_SECURITY.md)
- [Vorlage fuer den Datenschutz-Hinweis am Kamerabereich](docs/PRIVACY_NOTICE_TEMPLATE.md)

## Hardware

- Raspberry Pi 5 mit 64-bit Raspberry Pi OS oder kompatiblem Debian
- Hailo-10H
- Zwei V4L2-kompatible USB-Kameras
- Empfohlen: stabile Kamera-Pfade unter `/dev/v4l/by-path/` oder `/dev/v4l/by-id/`

## Installation

```bash
git clone <repo> Ki-kammera-pi
cd Ki-kammera-pi
./scripts/install.sh
./scripts/check_hardware.sh
```

## HailoRT pruefen

```bash
hailortcli --version
hailortcli fw-control identify
```

Wenn diese Befehle fehlen oder kein Geraet melden, startet die App, aber Hailo-Inferenz bleibt sichtbar nicht bereit.

## Kameraerkennung

```bash
v4l2-ctl --list-devices
ls -l /dev/v4l/by-path/
ls -l /dev/video*
```

Die GUI kann Kameras automatisch erkennen oder manuell pro Kamera auswaehlen. Metadaten-Nodes wie `/dev/video1` oder `/dev/video3` werden nicht als Bildquellen verwendet, wenn sie keine Frames liefern.

## Programmstart

Vor dem ersten Kamerastart muessen Rechtsgrundlage, Zweck, Verantwortlicher, Kontakt und der sichtbar angebrachte Datenschutzhinweis in `config/config.yaml` dokumentiert werden. Ohne diese Freigabe startet die Kameraverarbeitung nicht. Details: [Datenschutz- und Sicherheitskonzept](docs/PRIVACY_AND_SECURITY.md).

```bash
./scripts/start.sh
```

Alternativ:

```bash
PYTHONPATH=src python3 -m visitor_counter.app --project-root "$PWD"
```

## Desktop-Icon

Auf dem Raspberry Pi:

```bash
./scripts/install_desktop_icon.sh
```

Das erstellt einen Desktop- und App-Menü-Launcher.

## Historische V2-Zielarchitektur

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
