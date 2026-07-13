# Deployment and Recovery

Datum: 2026-07-02

## Backups

Die folgenden historischen Backups koennen Alt-Daten oder alte unsichere Konfigurationen enthalten. Vor Produktivbetrieb inventarisieren, verschluesseln, mit einer dokumentierten Frist versehen und nach Ablauf sicher loeschen; nicht ungeprueft wiederherstellen.

Vor den Änderungen wurde ein inkrementelles Backup erstellt:

`/home/raspibob/personenzaehler_backups/incremental_20260702T132829Z`

Das vorhandene Vollbackup blieb unverändert:

`/home/raspibob/personenzaehler_backups/full_20260702T122836Z`

## Produktiver Zustand

Die Anwendung ist auf fail-closed YOLO26x konfiguriert:

- erlaubte Detektor-HEF: `models/yolo26x_person_hailo10h_640.hef`
- produktive Fallbacks: deaktiviert
- YOLO11x: nur manuelle Rollback-/Vergleichsdatei, kein stiller Ersatz
- OSNet: installiert und hardwaregetestet

## Systemd

Projekt-Units:

- `systemd/visitor-counter.service`
- `systemd/visitor-counter-user.service`
- `systemd/visitor-counter-status-api.service`

Die Installation nach `/etc/systemd/system` konnte nicht abgeschlossen werden, weil das verfügbare SSH-Passwort nicht für `sudo` akzeptiert wurde.

Admin-Schritte auf BOB:

```bash
sudo install -m 0644 /home/raspibob/PersonenZ-hler/systemd/visitor-counter.service /etc/systemd/system/visitor-counter.service
sudo install -m 0644 /home/raspibob/PersonenZ-hler/systemd/visitor-counter-status-api.service /etc/systemd/system/visitor-counter-status-api.service
sudo install -d -m 0700 /etc/personenzaehler
sudo /home/raspibob/PersonenZ-hler/.venv/bin/python /home/raspibob/PersonenZ-hler/scripts/generate_secrets.py --output /etc/personenzaehler/api.env
sudo systemctl daemon-reload
sudo systemctl enable visitor-counter-status-api.service
sudo systemctl restart visitor-counter-status-api.service
```

## YOLO26x-HEF-Installation nach externer Kompilierung

Auf dem x86_64-Compilerhost:

```bash
cd yolo26x_hailo10h
./scripts/run_compile.sh
```

Danach auf BOB installieren:

```bash
./scripts/install_on_bob.sh build/yolo26x_person_hailo10h_640.hef /home/raspibob/PersonenZ-hler
```

Anschließend ausführen:

```bash
cd /home/raspibob/PersonenZ-hler
. .venv/bin/activate
hailortcli parse-hef models/yolo26x_person_hailo10h_640.hef
python -m pytest
python -m pytest -q -m hardware
```
