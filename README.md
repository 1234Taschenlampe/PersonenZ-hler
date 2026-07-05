# YOLO26m Dual-Kamera Besucherzaehler

Native PySide6-Desktop-Anwendung fuer einen Raspberry Pi 5 mit Hailo-10H und zwei Kameras.

Das Laufzeitsystem verwendet das YOLO26m COCO Detection HEF fuer Hailo-10H und filtert auf COCO-Klasse `person`. Es soll keine CPU-Inferenz, OpenCV-DNN, Dummy-Daten oder Pose-HEFs als Ersatz fuer die produktive Detektion verwenden.

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

Das erstellt:

```text
~/Desktop/Personenzaehler.desktop
~/.local/share/applications/personenzaehler.desktop
```

Der Launcher verwendet `scripts/start_gui.sh`, startet den vorhandenen `visitor-counter.service` bei Bedarf und verhindert doppelte GUI-Starts.

## GUI-Bedienung

Die Anwendung zeigt Kamera 1 links und Kamera 2 rechts. Sie zeigt Livebilder, Zaehlwerte, Modellstatus, Kameraauswahl, Diagnosewerte und Steuerbuttons.

Wichtige Zaehlwerte:

- `global inside`: aktuell stabil anwesende globale Personen
- `global in`: bestaetigte globale Eintritte
- `global out`: bestaetigte globale Austritte
- `camera 1/2 visible`: aktuell sichtbare Personen pro Kamera
- `suppressed`: unterdrueckte Doppelzaehlungen
- `uncertain`: unsichere Ereignisse

## Zaehllogik

Die globale Live-Zaehlung ist von der Anzeige sichtbarer Personen getrennt. Eine Person wird erst nach mehreren bestaetigten Frames als `inside` gezaehlt. Wenn sie verschwindet, wartet die Pipeline eine kurze Grace-Zeit, bevor `inside` sinkt und `global out` steigt.

Vor Tracking und ReID werden nur echte Personendetektionen mit ausreichender Konfidenz, sinnvoller Groesse und plausibler Box-Form verwendet. Dadurch werden kurze Fehlklassifikationen und Tracker-Flackern nicht direkt gezaehlt.

Es werden keine Gesichter erkannt, keine Namen gespeichert und keine dauerhaften biometrischen Gesichtsdaten abgelegt.

## Datenbank

Die lokale SQLite-Datenbank nutzt WAL-Modus, Foreign Keys, Transaktionen und idempotente Initialisierung. Live-Global-Counter werden in `global_counts` gespiegelt, damit GUI und Neustart dieselben Werte sehen.

## Tests

Normale Tests:

```bash
pytest
```

Hardwaretests auf dem Raspberry Pi:

```bash
pytest -m hardware
```

## Deployment auf den Raspberry Pi

Wenn der Pi erreichbar ist:

```powershell
.\tools\deploy_pi_live_counter_fix.ps1
```

Das Skript kopiert die relevanten Fix-Dateien auf den Pi, fuehrt die wichtigsten Tests aus, startet `visitor-counter.service` neu und zeigt relevante Logzeilen.

## systemd Autostart

User-Service auf dem Raspberry Pi:

```bash
systemctl --user status visitor-counter.service
systemctl --user restart visitor-counter.service
journalctl --user -u visitor-counter.service -f
```

System-Service, falls genutzt:

```bash
sudo cp systemd/visitor-counter.service /etc/systemd/system/visitor-counter.service
sudo systemctl daemon-reload
sudo systemctl enable visitor-counter.service
sudo systemctl start visitor-counter.service
```

## Fehlerdiagnose

```bash
./scripts/check_hardware.sh
PYTHONPATH=src python3 -c "from pathlib import Path; from visitor_counter.diagnostics import collect_diagnostics; collect_diagnostics(Path.cwd())"
cat logs/diagnostics_report.json
```

## GitHub Pages Konzeptseite

`index.html` stammt aus der vorherigen GitHub-`main`-Historie und beschreibt eine animierte Konzeptseite fuer das KI-Kameraprojekt. Sie ist nicht der produktive Raspberry-Pi-Runtime-Code.
