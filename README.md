# YOLO26m Dual-Kamera Besucherzaehler

Native PySide6-Desktop-Anwendung fuer einen Raspberry Pi 5 mit Hailo-10H und zwei Kameras.

Das Laufzeitsystem verwendet das YOLO26m COCO Detection HEF fuer Hailo-10H und filtert auf COCO-Klasse `person`. Es soll keine CPU-Inferenz, OpenCV-DNN, Dummy-Daten oder Pose-HEFs als Ersatz fuer die produktive Detektion verwenden.

## Zaehlkonzept

Die produktiven Zaehlwerte sind klar getrennt:

- **Aktuell im Gebaeude:** steigt bei einem bestaetigten Eintritt um 1 und sinkt bei einem bestaetigten Austritt um 1.
- **Besucher heute (eindeutig):** dieselbe Person soll pro lokalem Kalendertag nur einmal gezaehlt werden. Dafuer wird OSNet-ReID verwendet.
- **Eintritte gesamt:** jeder bestaetigte Eintritt erhoeht diesen persistenten Zaehler.
- **Austritte gesamt:** jeder bestaetigte Austritt erhoeht diesen persistenten Zaehler.
- **Durchfluss gesamt:** `Eintritte gesamt + Austritte gesamt`.

Die Belegung wird damit nicht mehr aus der blossen Sichtbarkeit in einem Kamerabild abgeleitet. Sichtbare Personen bleiben ein Diagnosewert; die Belegung aendert sich nur durch akzeptierte Linienuebertritte.

Fuer den eindeutigen Tageszaehler werden Re-ID-Embeddings nur fuer den aktiven Tag vorgehalten. Ist `VISITOR_COUNTER_DATA_KEY` gesetzt, werden diese Tagesprofile verschluesselt lokal in `data/daily_unique.sqlite3` abgelegt, damit ein Neustart nicht automatisch zu Doppelzaehlungen fuehrt. Beim Tageswechsel werden alte Tagesprofile geloescht. Ohne Schluessel arbeitet der Tageszaehler nur im RAM und ist nach einem Neustart nicht vollstaendig deduplizierungssicher.

## Privacy & GDPR

Das Projekt ist auf **lokale Verarbeitung und datenschutzfreundliche Voreinstellungen** ausgelegt. Im sicheren Standardbetrieb werden Kamerabilder nur fuer die laufende Personenerkennung verarbeitet und nicht dauerhaft als Video oder Einzelbild gespeichert. Gesichtserkennung und Namenszuordnung sind nicht vorgesehen. Granulare Personenereignisse sind standardmaessig deaktiviert.

Der optionale bzw. fuer den eindeutigen Tageszaehler aktivierte OSNet-ReID-Mechanismus verarbeitet Merkmalsvektoren aus dem Erscheinungsbild einer Person, um Wiederholungsbesuche am selben Tag zu erkennen. Diese Re-ID-Profile werden nicht als dauerhaftes Personenregister verwendet: sie gelten nur fuer den aktiven Kalendertag, werden lokal verarbeitet und bei vorhandener Persistenz verschluesselt gespeichert. Vor einem realen Einsatz muss der Betreiber die datenschutzrechtliche Zulaessigkeit dieses Re-ID-Zwecks gesondert pruefen.

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

Fuer Raspberry Pi OS/Debian steht ein zusammengefasster Installer bereit:

```bash
./scripts/install_linux_app.sh
```

Er installiert die normalen Linux-Abhaengigkeiten, erstellt die Python-Umgebung mit Zugriff auf systemweite Hailo-Bindings, erzeugt lokale Secrets, installiert Desktop-Starter und Autostart und prueft HailoRT. Fehlt HailoRT auf Raspberry Pi OS, versucht der Installer das offizielle `hailo-all`-Paket zu installieren.

Die projektspezifischen HEF-Dateien muessen unter folgenden Pfaden vorhanden sein:

```text
models/yolo26m_detection_hailo10h_640.hef
models/osnet_x1_0_hailo10h.hef
```

Manuelle Installation:

```bash
./scripts/install.sh
./scripts/check_hardware.sh
```

## HailoRT pruefen

```bash
hailortcli --version
hailortcli fw-control identify
```

Wenn diese Befehle fehlen oder kein Geraet melden, startet die App nicht in den produktiven Detektions-/Re-ID-Betrieb.

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
./scripts/start_gui.sh
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

Das erstellt:

```text
~/Desktop/Personenzaehler.desktop
~/.local/share/applications/personenzaehler.desktop
```

Der Launcher verwendet `scripts/start_gui.sh`, startet den vorhandenen `visitor-counter.service` bei Bedarf und verhindert doppelte GUI-Starts.

## GUI-Bedienung

Die Anwendung zeigt standardmaessig keine Livebilder. Die Kameraflaechen bleiben im Datenschutzmodus verdeckt; Zaehler, Modellstatus, Kameraauswahl und Diagnosewerte bleiben sichtbar. Eine Vorschau muss bewusst aktiviert werden und bleibt anonymisiert.

Wichtige Zaehlwerte:

- `Aktuell im Gebaeude`
- `Besucher heute (eindeutig)`
- `Durchfluss gesamt`
- `Eintritte gesamt`
- `Austritte gesamt`
- sichtbare Personen pro Kamera
- unterdrueckte Doppelzaehlungen
- unsichere Ereignisse

## Datenbank

Die lokale SQLite-Hauptdatenbank speichert standardmaessig nur aggregierte Zaehler. Granulare Ereignisse sind aus; optional aktivierte Ereignisse erfordern einen externen Verschluesselungsschluessel, werden pseudonymisiert und nach kurzer Frist automatisch geloescht.

Der eindeutige Tageszaehler verwendet bei vorhandenem `VISITOR_COUNTER_DATA_KEY` zusaetzlich `data/daily_unique.sqlite3`. Dort liegen nur verschluesselte Re-ID-Embeddings des aktiven Tages sowie Zeitstempel. Alte Tagesprofile werden beim Tageswechsel geloescht.

## Tests

Normale Tests:

```bash
pytest
```

Hardwaretests auf dem Raspberry Pi:

```bash
pytest -m hardware
```

Secret-Erzeugung, TLS, Rollen, Export und Loeschung sind in [docs/PRIVACY_AND_SECURITY.md](docs/PRIVACY_AND_SECURITY.md) beschrieben.

## Deployment auf den Raspberry Pi

Wenn der Pi erreichbar ist:

```powershell
.\tools\deploy_pi_live_counter_fix.ps1
```

Das Skript kopiert die relevanten Fix-Dateien auf den Pi, fuehrt die wichtigsten Tests aus, startet `visitor-counter.service` neu und zeigt relevante Logzeilen.

## systemd Autostart

Der empfohlene User-Service wird durch `scripts/install_autostart.sh` erzeugt. Er laedt die lokalen Secrets aus:

```text
~/.config/personenzaehler/api.env
```

Status und Neustart:

```bash
systemctl --user status visitor-counter.service
systemctl --user restart visitor-counter.service
journalctl --user -u visitor-counter.service -f
```

## Fehlerdiagnose

```bash
./scripts/check_hardware.sh
PYTHONPATH=src python3 -c "from pathlib import Path; from visitor_counter.diagnostics import collect_diagnostics; collect_diagnostics(Path.cwd())"
cat logs/diagnostics_report.json
```

## GitHub Pages Konzeptseite

`index.html` stammt aus der vorherigen GitHub-`main`-Historie und beschreibt eine animierte Konzeptseite fuer das KI-Kameraprojekt. Sie ist nicht der produktive Raspberry-Pi-Runtime-Code.
