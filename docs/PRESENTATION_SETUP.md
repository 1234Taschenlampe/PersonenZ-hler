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
- Die beiden Hailo-10H-HEFs `yolo26m_detection_hailo10h_640.hef` und
  `osnet_x1_0_hailo10h.hef` werden **automatisch direkt aus dem offiziellen
  Hailo Model Zoo** heruntergeladen. Ihre bestehenden SHA-256-Referenzwerte
  werden geprüft; fehlender Internetzugang und inkompatible HailoRT-Versionen
  werden ausdrücklich gemeldet. Credits und Lizenzbedingungen:
  [MODEL_SOURCES_AND_CREDITS.md](MODEL_SOURCES_AND_CREDITS.md).
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

**Ablauf (7 Stufen):** 1. Plattform/CPU/Raspberry-Pi-5 erkennen; 2. nur fehlende
Debian-Pakete installieren (Hailo-10H ausschließlich auf erkanntem Pi 5 ARM64);
3. Python-Umgebung einmalig erstellen und nur bei geändertem Abhängigkeitsstand
aktualisieren; 4. Konfiguration/Schlüssel nur bei erstmaligem Fehlen anlegen;
5. beide Original-HEFs laden und SHA-256 prüfen; 6. Desktop-Starter und
Benutzer-Systemd-Dienste nur bei geändertem Inhalt aktualisieren; 7. Modell-
und Hailo-Status prüfen.

Eine erneute Ausführung verändert keine vorhandenen Kameraeinstellungen,
API-Schlüssel, Datenbanken oder nicht passende HEFs. Der Paketindex wird bei
Bedarf höchstens einmal täglich aktualisiert. Eine laufende Kamera-Pipeline
wird nur nach einer tatsächlichen Code- oder Dienstaktualisierung neu gestartet.
Git-Updates erfolgen ausschließlich per Fast-Forward; lokale Codeänderungen
werden nicht überschrieben.

Für Diagnose vor der Einrichtung (ohne Änderungen):
```bash
bash ~/.local/share/personenzaehler/app/scripts/quick_install.sh --dry-run
```

Für Weiterbetrieb ohne Git-Update, etwa vor einer Demonstration:
```bash
bash ~/.local/share/personenzaehler/app/scripts/quick_install.sh --offline
```

Der Zähldienst darf erst ausgeführt werden, wenn die beiden Kameraquellen
sowie Modell- und Postprocessing-Dateien konfiguriert sind. Die entsprechende
`ExecCondition` verhindert Neustartschleifen vor der Ersteinrichtung.
Die lokale API bleibt aus Sicherheitsgründen an `127.0.0.1` gebunden.
Der Einrichtungsassistent muss Kamera-Zugangsdaten erhalten; unbekannte
Passwörter können nicht automatisch ermittelt werden.

Diagnose (bei Fehlern):

```bash
~/.local/share/personenzaehler/app/scripts/check_hardware.sh
systemctl --user status visitor-counter.service --no-pager
systemctl --user status personenzaehler.service --no-pager
systemctl --user status personenzaehler-mobile-api.service --no-pager
journalctl --user -u personenzaehler.service -n 100 --no-pager
```

Der Installer lädt automatisch beide offiziellen HEFs herunter und prüft ihre
SHA-256-Werte; per **KI & Hardware** können sie später einzeln nachgeladen
werden. Anschließend müssen Treiber/Firmware und die echte Inferenz auf dem
Zielgerät geprüft werden. Bei Problemen ist derselbe Installer erneut
aufrufbar, ohne bereits eingerichtete Komponenten zu überschreiben.

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

## Verbesserte Kamerasuche und Verbindung

Die Seite **Kameras** trennt jetzt eindeutig:

- **USB-Kameras**: nur lokale USB-Webcams; eine Anzeige `0 USB-Webcams`
  sagt *nichts* über bereits verbundene Reolink-IP-Kameras aus.
- **IP-Kameras suchen**: RTSP-TCP-Portsuche (554/8554) und ONVIF-Discovery
  (Multicast UDP 3702) im eigenen LAN. Ein ONVIF-Fund bestätigt **noch
  keine Videobilder**. Die Suche erhält gespeicherte Kamerakonfigurationen.
- **Kamera 1/2**: die obere Statuszeile nennt die tatsächlich konfigurierten
  Quellen und wie viele aktuell gültige Videobilder liefern. Eine Kamera
  gilt erst nach dekodiertem Frame als **ONLINE**.
- **Verbindung testen**: derselbe RTSP-over-TCP-Videopfad wie der
  Zähldienst, mit definierten Open-/Read-Timeouts. Fehlertexte unterscheiden
  fehlgeschlagene Verbindung und fehlendes Videobild.

Wenn nur eine der beiden Reolink-Kameras Bilder liefert:
1. IP-Adresse und Port der zweiten Kamera unter Kameras prüfen.
2. Kamera in Reolink-App oder Weboberfläche: RTSP aktiviert, Benutzerkonto
   besitzt Stream-Zugriff, Haupt- und Substream aktiv.
3. Zuerst **Substream**, falls dieser nicht funktioniert **Hauptstream**
   testen. Bei 10 FPS ist der Stream nicht zwangsläufig defekt, solange
   echte fortlaufende Bilder eintreffen.
4. Bei mehreren Routern sicherstellen, dass der Pi **beide** IP-Adressen
   tatsächlich erreicht. ONVIF-Multicast überquert meist keine Router.
5. **Verbindung testen** anklicken, danach **Änderungen speichern** und
   im Bereich System den Zähldienst neu starten. Die GUI-Suche allein
   ersetzt keine laufende Dienstkonfiguration.

## Richtungsabhängige Zählung an beiden Türen

**Beide Kameras erkennen jeweils beide Richtungen**. „Eingangsbereich“ und
„Ausgangsbereich“ beschreiben nur den Standort, nicht die zulässige
Bewegungsrichtung. Sobald eine Person die korrekt eingestellte
A/B-Bewegungsrichtung nach innen passiert, wird sie als Eintritt bewertet;
in der Gegenrichtung als Austritt. Damit gilt auch:

- Ausgangstür als Eintritt genutzt → **+1** bei bestätigtem Eintritt
- Eingangstür als Ausgang genutzt → **−1** bei bestätigtem Austritt

Der grafische Dialog enthält nur die Entscheidung:
**„Welche Richtung führt ins Gebäude?“** Die Rückrichtung wird automatisch
als Ausgang festgelegt. Bereits gespeicherte einseitige Legacy-Presets
werden beim Laden kompatibel in eine bidirektionale Einstellung migriert.

Unter **„Wann wird gezählt?“** gibt es zwei Modi:

- **Linie/Seitenwechsel (empfohlen):** eine bestätigte Bewegung von A nach
  B beziehungsweise B nach A mit Hysterese zählt sofort.
- **Erst am Bildrand nach Verschwinden:** der Track muss zuvor stabil
  auf der anderen Seite der konfigurierten Linie gewesen sein, einen
  bestätigten Seitenwechsel ausführen und am tatsächlichen Frame-Rand
  aus dem Blickfeld verschwinden. Kurzzeitige Verdeckungen oder einfaches
  Verschwinden mitten im Raum zählen nicht.

Die Linie bleibt räumlich an der Türschwelle auszurichten. Die Darstellung
der Linie nutzt die konfigurierten Bildkoordinaten und wird bei verkleinerten
Reolink-Substreams auf die tatsächliche Auflösung umgerechnet.

**Wichtig:** Auch dieser Modus kann physikalisch nicht aus beliebigem
Verschwinden aus einem Kamerabild zweifelsfrei einen Ein- oder Austritt
ableiten. Kamera-Geometrie und Laufrichtung müssen anhand realer Passagen
festgelegt werden; bei zu schwacher Sicht auf beide Seiten der Tür können
Occlusions und Kameraübergänge zu Unsicherheit führen. Ein manueller
Test mit je fünf Passagen in beide Richtungen pro Kamera ist sinnvoll.

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
