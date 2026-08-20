# Installation und Upgrade

## Unterstütztes Ziel

Primär unterstützt werden Raspberry Pi 5, aktuelles 64-Bit Raspberry Pi OS (Trixie), Hailo-10H/AI HAT+ 2 und eine grafische Desktop-Sitzung. Der Trixie-Zielstand ist relevant, weil dort auch die ARM64-PySide6-Pakete verfügbar sind. Für Produktion werden HailoRT samt kompatibler Firmware sowie die vorgesehenen YOLO26m- und OSNet-HEFs benötigt. Die Herstellerinstallation folgt der [offiziellen Raspberry-Pi-Anleitung für AI-Software](https://www.raspberrypi.com/documentation/computers/ai.html).

## Grafische Installation

1. `personenzaehler_1.0.0_arm64.deb` aus dem CI-/Release-Artefakt laden.
2. Das Paket doppelklicken und im grafischen Paketinstaller installieren.
3. **PersonenZähler** im App-Menü öffnen.
4. Im First-Run-Assistenten Betreiberangaben, Kameras, API und Lizenz einrichten.
5. Unter **KI & Hardware** die beiden Hailo-10H-HEFs importieren und die Hardwareprüfung starten.
6. Unter **System** den Produktionsdienst starten.

PolicyKit zeigt bei geschützten Aktionen den normalen Systemdialog. Die Desktop-Anwendung selbst erhält keine Root-Rechte.

## Installierte Pfade

| Inhalt | Pfad |
|---|---|
| Programm | `/usr/lib/personenzaehler` |
| Starter | `/usr/bin/personenzaehler*` |
| Konfiguration | `/etc/personenzaehler/config.yaml` |
| API-/Datenschlüssel | `/etc/personenzaehler/api.env` (`0640`) |
| Lizenz | `/etc/personenzaehler/license.json` |
| öffentlicher Lizenzschlüssel | `/usr/share/personenzaehler/license_public_key.pem` |
| Modelle und Datenbank | `/var/lib/personenzaehler` |
| Cache | `/var/cache/personenzaehler` |
| Logs | `/var/log/personenzaehler` bzw. Journal |

Die Konfiguration enthält keine API-Tokens oder privaten TLS-/Lizenzschlüssel. Eingebettete Benutzername/Passwort-Kamera-URLs sollten vermieden werden; Diagnoseexporte redigieren sie zwar, eine sichere Kamera-Netzsegmentierung und dedizierte Zugangsdaten bleiben Betreiberaufgabe.

## Lizenz

Die GUI zeigt ihren Gerätefingerabdruck an und importiert signierte JSON-Lizenzen per Dateiöffnung oder über **Datenschutz → Lizenzdatei importieren**. Nur der öffentliche Ed25519-Schlüssel wird ausgeliefert. Ohne gültige Lizenz bleibt die GUI zur Einrichtung und Diagnose verfügbar, der Produktionsdienst startet jedoch nicht.

## Modelle und Hailo

Die Anwendung erwartet genau:

- `yolo26m_detection_hailo10h_640.hef`
- `osnet_x1_0_hailo10h.hef`

Der grafische Import kopiert nur reguläre `.hef`-Dateien auf feste Ziele und lässt die Hardwareprüfung danach Modell, SHA-256 und Hailo-Zustand anzeigen. Fehlende Herstellerkomponenten werden nicht durch CPU-Inferenz ersetzt.

## Upgrade

Ein neueres DEB wird im grafischen Paketinstaller über die bestehende Version installiert. `/etc/personenzaehler/config.yaml` ist als Conffile markiert; Datenbank, Modelle, Lizenz und Secrets liegen außerhalb des Programmcodes und bleiben erhalten. SQLite führt additive Migrationen beim Öffnen transaktional aus. Vor Produktiv-Upgrades empfiehlt sich ein gesichertes Backup der Konfiguration und aggregierten Datenbank.

## Deinstallation

Die Paketdeinstallation stoppt und deaktiviert die Dienste, entfernt aber bewusst keine Betreiberkonfiguration, Lizenz, Modelle oder Datenbank. Das verhindert unbeabsichtigten Datenverlust. Diese Daten können anschließend über die GUI bzw. die System-Paketverwaltung nach einer bewussten Entscheidung entfernt werden.

## AppImage-Bewertung

Ein AppImage ist technisch nicht der unterstützte Produktionsweg. HailoRT, Firmware, Geräteberechtigungen, systemd und PolicyKit sind systemgebundene Komponenten; ein eingebettetes Paket würde falsche Portabilität suggerieren. Das DEB prüft und integriert diese Grenzen nachvollziehbar.
