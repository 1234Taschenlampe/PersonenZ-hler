# Automatische GitHub-Updates der Raspberry-Pi-Quellinstallation

Der Raspberry Pi kann die **bereits installierte** Anwendung automatisch von
`1234Taschenlampe/PersonenZ-hler`, Branch `main`, aktualisieren. Nach einem
einmaligen manuellen Installations-/Updater-Setup übernimmt systemd die Checks.

## Aktivieren

Auf dem Pi, **im verwendeten Git-Checkout**, zum Beispiel
`~/.local/share/personenzaehler/app`:

```bash
cd ~/.local/share/personenzaehler/app
bash scripts/install_autostart.sh
systemctl --user enable --now personenzaehler-update.timer
systemctl --user list-timers personenzaehler-update.timer
```

Der vollständige Einmal-Installer `scripts/quick_install.sh` richtet den
Timer bei neuen Installationen ebenfalls ein. **Wichtig:** Die 10.10.2026 auf
BOB dokumentierte Installation hatte einen separaten Checkout unter
`/home/admin/personenzaehler-pr18`; dieser muss zuerst kontrolliert auf die
aktuelle `main`-Installation umgestellt werden. Keine zweite Installation
über eine aktive Installation legen, ohne vorher die Dienstpfade mit
`systemctl --user show personenzaehler.service -p ExecStart` zu prüfen.

Der Updater akzeptiert nur einen sauberen Git-Checkout auf `main` mit dem
festgelegten HTTPS-Origin. Ein PR-Branch, lokaler geänderter Code oder
divergierende Historie wird nicht automatisch ersetzt.

## Ablauf

- **Zeitplan:** 15 Minuten nach Systemstart und täglich um 03:00, 09:00,
  15:00 und 21:00 Uhr, jeweils mit einer zufälligen Verzögerung von
  bis zu 10 Minuten. Tagsüber wird nur geprüft; automatische Installation und
  Neustarts sind auf **02:00–05:00 Uhr Pi-Lokalzeit** begrenzt.
  Der nächste Termin steht in `list-timers`.
- **Keine Änderung:** Der Updater protokolliert nur die aktuelle Revision.
- **Neue Revision:** Download via `git fetch`, Freigabe nur bei grünen GitHub-
  CI-Jobs (Python 3.11, Python 3.12, Debian-Paket), Vorabprüfung des neuen
  Codes in einem separaten Git-Worktree und erst danach Fast-Forward auf `main`
  sowie Aufruf des idempotenten Installers.
  Fehlende Python-Abhängigkeiten und Modelle werden gemäß Installer bei Bedarf
  aktualisiert bzw. geprüft.
- **Aktivierung:** Vor dem Neustart wird geprüft, dass laufende Dienste
  tatsächlich auf denselben Git-Checkout zeigen. Bereits laufende Zähl-,
  API- und Desktopdienste werden über den Installer neu gestartet.
  Nachher müssen zuvor funktionierende Kameras erneut KI-Bilder verarbeiten. Bewusst gestoppte Zähldienste werden
  dadurch nicht ungefragt gestartet.
- **Fehler:** Bei Installations- oder Gesundheitsfehler versucht der Updater,
  den vorherigen Git-Stand und die alte Installation wiederherzustellen.
  Gelingt das nicht, bleibt der Fehler explizit protokolliert. Ein solcher
  Rollback ist kein vollständiges Betriebssystem-/Paket-Rollback.
- **Kein Netzwerk:** Abbruch und erneuter Versuch beim nächsten Timer;
  der laufende Zähldienst wird nicht angehalten.

Die Quelle, Konfiguration, Kamera-Zugangsdaten, Lizenz, API-Schlüssel und
Datenbank werden nicht bewusst überschrieben. Der Updater läuft als
unprivilegierter Benutzer-Systemdienst; fehlen neue Betriebssystempakete,
die Administratorrechte benötigen, ist eine manuelle Installation nötig.
CI-Fehler oder eine nicht erreichbare GitHub-Checks-API verhindern bewusst das
automatische Update. Der letzte bekannte, funktionierende Stand läuft weiter.

## Status und manuelle Prüfung

```bash
systemctl --user status personenzaehler-update.timer --no-pager
journalctl --user -u personenzaehler-update.service -n 80 --no-pager
cat ~/.local/state/personenzaehler/auto-update-status.json
python3 ~/.local/share/personenzaehler/app/scripts/auto_update.py --check-only
```

Eine sofortige Aktualisierung kann man über
`systemctl --user start personenzaehler-update.service` auslösen.
Außerhalb des Nachtfensters wird dabei **nur geprüft**. Für eine bewusste
sofortige Installation (kann die Videofeeds und die GUI neu starten):

```bash
python3 ~/.local/share/personenzaehler/app/scripts/auto_update.py --apply-now
```

## Vorführung: Updates vorübergehend sperren

Um einen automatischen Neustart während einer Demonstration zu verhindern:

```bash
mkdir -p ~/.config/personenzaehler
touch ~/.config/personenzaehler/auto-update.paused
```

Später wieder freigeben:

```bash
rm ~/.config/personenzaehler/auto-update.paused
systemctl --user start personenzaehler-update.service
```

Die Pause betrifft ausschließlich Updates, nicht Kameraerfassung, Erkennung
oder Personenzählung.
