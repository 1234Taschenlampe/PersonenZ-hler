# Dienstag: Abnahme auf dem Raspberry Pi 5 (Hailo-10H)

Dieses Dokument beschreibt die reale Abnahme. Die GitHub-CI prüft Quellcode
und Emulator, **nicht** zwei physische Reolink-Kameras, Hailo-Hardware oder ein
geroutetes Mesh-/Deco-Netz.

## Vor der Installation

- Raspberry Pi 5 mit 64-Bit Raspberry Pi OS (Trixie) und grafischer Sitzung.
- AI HAT+ 2 / Hailo-10H: offizielles **hailo-h10-all** (nicht hailo-all);
  nach Treiberinstallation ggf. den Pi neu starten.
- Zwei Reolink-LAN-Kameras, für die RTSP in der Kamera aktiviert ist.
- Zugriffsberechtigungen und möglichst feste DHCP-Adressen für beide Kameras.
- **Zwei passende, bereits kompilierte Hailo-10H-HEF-Dateien**:
  `yolo26m_detection_hailo10h_640.hef` und `osnet_x1_0_hailo10h.hef`.
  Die HEFs sind im Repository **nicht** vorhanden; der Installer kann sie
  nicht automatisch erzeugen oder seriös durch andere Modelle ersetzen.
- Die GitHub-Änderungen müssen zuvor in `main` übernommen sein.

## Installation auf dem Pi

In einem Terminal der Pi-Desktopumgebung:

```bash
curl -fsSL https://raw.githubusercontent.com/1234Taschenlampe/PersonenZ-hler/main/scripts/quick_install.sh -o /tmp/personenzaehler-install.sh
bash /tmp/personenzaehler-install.sh
```

Installationsziel: `~/.local/share/personenzaehler/app`. Programm im
Himbeer-/Anwendungsmenü unter **Personenzaehler** starten. Daten und
Konfiguration liegen für diese Installation im Benutzerprofil.
Der Installer aktualisiert bei Wiederholung nur per Fast-Forward und verweigert
das Überschreiben lokal geänderter Quellcodedateien. Das ist **keine**
automatische Übernahme ungetesteter GitHub-Commits.

Diagnose (bei Fehlern):

```bash
~/.local/share/personenzaehler/app/scripts/check_hardware.sh
systemctl --user status visitor-counter.service --no-pager
systemctl --user status personenzaehler.service --no-pager
systemctl --user status personenzaehler-mobile-api.service --no-pager
journalctl --user -u personenzaehler.service -n 100 --no-pager
```

Das Skript zeigt bei fehlenden Modellen Hinweise an, installiert die beiden
projektspezifischen HEFs aber nicht. Nach dem Import unter **KI & Hardware**
müssen Modell, Firmware und Inferenzfähigkeit auf dem Zielgerät geprüft werden.

## Zwei Reolink-Kameras verbinden

1. In **Kameras** → **Netzwerk scannen** suchen. Ohne CIDR untersucht der
   Scanner private IPv4-Netze, die direkt am Pi angeschlossen sind; ein
   explizites `192.168.x.0/24` durchsucht ein geroutetes anderes Privatnetz.
2. Falls nichts gefunden wird: Router-Netz, Subnetzmasken, Kamera-IP,
   Inter-Router-Routing und TCP-Port 554 prüfen. Der Scan erkennt nur offene
   RTSP-Ports, keine Identität oder gültige Stream-Anmeldung.
3. Kamera-IP, Benutzername und Passwort in der jeweiligen Kamerakarte eingeben,
   `Substream` wählen und **Reolink-Quelle aus IP übernehmen** drücken.
   Alternativ vollständige RTSP-URL in **Kameraquelle** eingeben.
4. **Verbindung testen**; bei Erfolg beide Kameraquellen speichern.
   Rollen Eingang/Ausgang und die tatsächlichen Bewegungsrichtungen prüfen.
5. Prüfen, ob die Kamera über RTSP tatsächlich Frames liefert. Wird sie nur im
   Scan gefunden, ist die Videofunktion **noch nicht** nachgewiesen.

Typische Reolink-URL: `rtsp://BENUTZER:PASSWORT@KAMERA-IP:554/Preview_01_sub`.
Passwörter mit Sonderzeichen durch die integrierte IP-Hilfe eingeben; das
Programm kodiert sie für die URL. Niemals Passwörter in Logs/Screenshots
zeigen.

## Abnahme mit echten Personen (nicht mit Emulator)

- Beide Kameras liefern dauerhaft Bilder, Rollen und Geometrie sind korrekt.
- Jede Person überschreitet die konfigurierte Linie bewusst in beide Richtungen.
- Fünf einzeln kontrollierte Eintritte ergeben fünf Eintritte, fünf Austritte
  entsprechend fünf Austritte; keine Doppelzählung beim Verharren.
- Gleichzeitige Personen, Drehrichtung, kurzzeitige Verdeckung und Rückkehr
  einmal gezählter Personen testen (getrennte Tages-/Durchflussmetriken).
- Pi neu starten: GUI ist im Anwendungsmenü, Dienst startet wieder, aggregierte
  Daten bleiben erhalten, RTSP verbindet sich nach Netzausfall wieder.
- Die Android-App muss den Pi **über ihr eigenes erreichbares WLAN/LAN**
  erreichen können; mDNS-Erkennung funktioniert nicht zwangsläufig über Router.
  Bei isoliertem Netz die IP manuell in der App eingeben. Für den API-Zugriff
  müssen dessen vorgesehene Authentifizierungs- und TLS-Einstellungen passen.
- Keine echten Abnahmeergebnisse behaupten, bevor der Test am Pi erfolgt.

## Präsentationssicherheit

Für die Vorführung zuerst den **echten Livepfad** inklusive Kamera, Hailo,
Erkennung und Zählereignis verifizieren. Falls die Modelle oder Netzwerkroute
nicht rechtzeitig bereitstehen, den **Emulator ausdrücklich als Demo**
kennzeichnen und nicht als Liveerkennung ausgeben. Die App zeigt dann nur
demonstrierbare Softwarefunktionen.

Die optionalen Betreiberfelder in der UI entbinden nicht von rechtlichen
Pflichten beim tatsächlichen Kameraeinsatz.

## Dienstarchitektur bei Installation aus dem Quellcode

Der Installer erzeugt getrennte **Benutzer-Systemdienste**:

- `visitor-counter.service`: grafische Anwendung in der Pi-Desktop-Sitzung;
- `personenzaehler.service`: die eigentliche Kameraverarbeitung/Inference; wird
  im Bereich **System** gestartet und bleibt nach dem Einrichten bei Neustarts aktiviert;
- `personenzaehler-mobile-api.service`: lokale Status-API (automatisch
  aktiviert); externe Android-Verbindungen benötigen eine erreichbare, sicher
  konfigurierte TLS-/Token-API-Bindung.

Alle Komponenten nutzen die im Benutzerprofil gespeicherte Konfiguration.
Bei Änderungen der Netzwerksicherheit den API-Dienst neu starten:

```bash
systemctl --user restart personenzaehler-mobile-api.service
```

Die App verbindet sich **nicht von selbst mit einem fremden WLAN**. Handy und Pi
müssen routbar verbunden sein. Eine lokale API auf `127.0.0.1` ist vom Handy
aus nicht erreichbar; ein ungeschütztes HTTP-Binding wird nicht automatisch
freigeschaltet.
