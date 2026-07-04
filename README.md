# YOLO26x Dual-Kamera Besucherzaehler

Native PySide6-Desktop-Anwendung fuer einen Raspberry Pi 5 mit Raspberry Pi AI HAT+ 2, Hailo-10H und zwei Kameras.

## Hardware

- Raspberry Pi 5, 64-bit Raspberry Pi OS oder kompatibles Debian
- Raspberry Pi AI HAT+ 2 mit Hailo-10H
- Zwei V4L2-kompatible Kameras
- Empfohlen: stabile Kamera-Pfade unter `/dev/v4l/by-path/`

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

Wenn diese Befehle fehlen oder kein Geraet melden, ist die App startbar, aber Hailo-Inferenz bleibt sichtbar nicht bereit.

## Kameraerkennung

```bash
v4l2-ctl --list-devices
ls -l /dev/v4l/by-path/
ls -l /dev/video*
```

Die GUI kann Kameras automatisch erkennen oder manuell pro Kamera auswaehlen.

## YOLO26x Export und Hailo-10H Kompilierung

Auf einem x86-64-Ubuntu-System mit Hailo Dataflow Compiler:

```bash
python3 -m venv .venv-hailo
. .venv-hailo/bin/activate
pip install -r tools/hailo_compile_yolo26x/requirements.txt
cp /path/to/yolo26x.pt models/yolo26x.pt
tools/hailo_compile_yolo26x/compile_yolo26x.sh data/calibration
```

Zielausgabe:

```text
models/yolo26x_hailo10h_640.hef
```

Kopiere diese HEF-Datei auf den Raspberry Pi in denselben Pfad.

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

Der Launcher verwendet `scripts/start_gui.sh`, startet die `.venv`, schreibt `logs/gui_launcher.log`, verhindert Mehrfachstarts per Lock/PID-Datei und zeigt Startfehler grafisch an, wenn `zenity`, `kdialog` oder PySide6 verfuegbar sind.

## GUI-Bedienung

Die Anwendung zeigt Kamera 1 links und Kamera 2 rechts. Bounding Boxes, Track-IDs und Zaehl-Linien werden in den Kamerabildern angezeigt. Wenn `models/yolo26x_hailo10h_640.hef` fehlt oder HailoRT nicht geladen werden kann, zeigt die Kopfzeile den fehlenden YOLO26x-HEF-Status.

Unter `Kameraeinstellungen` koennen Kamera 1 und Kamera 2 ueber benutzerfreundliche Eintraege mit Hersteller, Modell, stabilem `/dev/v4l/by-id`- oder `/dev/v4l/by-path`-Pfad, aktuellem `/dev/videoX`-Knoten, Hauptaufloesung und Frei/Belegt-Status ausgewaehlt werden. Dieselbe Kamera kann nicht doppelt zugewiesen werden.

Bedienelemente:

- Start, Stopp, Neustart
- Zaehler zuruecksetzen
- Kameras neu erkennen
- Konfidenz, Tracking und Konsensfenster einstellen
- Einstellungen speichern
- Diagnosebericht erstellen

## Linien kalibrieren

Die gelbe Linie in jedem Kamerabild kann an beiden Endpunkten mit der Maus verschoben werden. Einstellungen werden in `config/config.yaml` gespeichert.

## Dual-Kamera-Konsens

Jede Kamera erzeugt lokale Linienueberquerungen. Die Konsenslogik vergleicht Kamera-ID, Richtung, Zeitfenster, Zone und Bounding-Box-Groesse. Starke Treffer werden als Doppelzaehlung unterdrueckt, schwache Treffer als unsicher protokolliert. Es werden keine Gesichter erkannt und keine biometrischen Gesichtsdaten gespeichert.

## Modell-Cleanup

Zuerst trocken laufen lassen:

```bash
PYTHONPATH=src python3 scripts/cleanup_old_models.py
```

Danach pruefen:

```bash
cat logs/model_inventory_before_cleanup.json
cat logs/models_to_delete.json
cat logs/model_cleanup_result.json
```

Nur wenn der Plan korrekt ist:

```bash
PYTHONPATH=src python3 scripts/cleanup_old_models.py --delete
```

Das Skript schuetzt Systempfade wie `/boot`, `/etc`, `/lib`, `/usr/lib` und behaelt `yolo26x.pt`, `yolo26x.onnx`, `yolo26x.har`, `yolo26x.hef` und `yolo26x_hailo10h_640.hef`.

Benutzer-Caches werden nur mit expliziter Option durchsucht:

```bash
PYTHONPATH=src python3 scripts/cleanup_old_models.py --include-user-caches
```

## Tests

Normale Tests:

```bash
pytest
```

Hardwaretests auf dem Raspberry Pi:

```bash
pytest -m hardware
```

Performance-Smoke-Report:

```bash
PYTHONPATH=src python3 scripts/performance_smoke.py --duration 60
cat logs/performance_report.json
```

## systemd Autostart

Pfad im Service ggf. anpassen, dann:

```bash
sudo cp systemd/visitor-counter.service /etc/systemd/system/visitor-counter.service
sudo systemctl daemon-reload
sudo systemctl enable visitor-counter.service
sudo systemctl start visitor-counter.service
```

Status und Logs:

```bash
systemctl status visitor-counter.service
journalctl -u visitor-counter.service -f
tail -f logs/application.log
tail -f logs/errors.log
```

Stoppen:

```bash
sudo systemctl stop visitor-counter.service
```

## Fehlerdiagnose

```bash
./scripts/check_hardware.sh
PYTHONPATH=src python3 -c "from pathlib import Path; from visitor_counter.diagnostics import collect_diagnostics; collect_diagnostics(Path.cwd())"
cat logs/diagnostics_report.json
```

## Deinstallation

```bash
sudo systemctl disable --now visitor-counter.service || true
sudo rm -f /etc/systemd/system/visitor-counter.service
sudo systemctl daemon-reload
rm -rf .venv data/visitor_counter.sqlite3
```

Loesche `models/` nur, wenn keine HEF-, HAR-, ONNX- oder Ausgangsmodelle mehr benoetigt werden.
