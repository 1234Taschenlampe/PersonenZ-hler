# BOB: Deployment und Hardwareprüfung vom 10.10.2026

## Installation und Datenerhalt

- Ausgangspunkt: PR #18, Branch `fix/2026-10-10-camera-debug-and-controls`, Commit `ce01950`.
- Zielgerät über Ethernet bestätigt: Hostname BOB, Raspberry Pi 5 Model B Rev 1.1, Debian 13 ARM64, Hailo-10H am PCIe-Bus und `/dev/hailo0`, HailoRT/Firmware 5.1.1.
- Alte, lokal veränderte Installation bleibt unter `/opt/personenzaehler-src` erhalten. Neue Installation: `/home/admin/personenzaehler-pr18`, erstellt mit `scripts/install_linux_app.sh`.
- Konfiguration, Datenbanken, Schlüssel, Lizenz, Modelle und Dienste vorab in einem zugriffsgeschützten TAR-Archiv gesichert und Archivintegrität geprüft. Archiv-SHA-256: `88ca26d30344b8c2fb1a3da2077f556c380629951aaa0be90b507d9c2772face`.
- Benutzerkonfiguration verwendet weiterhin die vorhandene Datenbank in `/var/lib/personenzaehler`. Der zugehörige Datenverschlüsselungsschlüssel wurde aus der bisherigen Systemkonfiguration übernommen; bestehende API-Tokens wurden beibehalten. Zugangsdaten und lokale Lizenzschlüssel sind nicht Bestandteil dieses Commits.
- Desktop, Zähldienst und lokale API laufen als Benutzer-Systemdienste. Bestehende Systemdienste waren deaktiviert und bleiben unberührt.

## Reale Kamera- und Modellmessungen

| Prüfung | Ergebnis |
| --- | --- |
| Hauptstreams beider Kameras | Authentifiziertes RTSP über TCP; gültige Frames mit 2560 × 1920 Pixeln |
| Substreams beider Kameras | Gültige Frames mit 640 × 480 Pixeln; 179 bzw. 207 Frames in etwa 22 Sekunden einschließlich Verbindungsaufbau |
| Hauptstream-FPS, abschließendes 20-Sekunden-Fenster | Kamera 1: 24,78 FPS; Kamera 2: 20,02 FPS |
| YOLO26m auf Hailo-10H | Initialisierung und Inferenz mit echtem Kamerabild erfolgreich; 118 weitere Inferenzaufrufe im Messfenster |
| OSNet x1.0 auf Hailo-10H | Initialisierung und Inferenz mit Bildausschnitt erfolgreich; 512 Dimensionen, Norm etwa 1,0, 7,55 ms im Einzelaufruf |
| Laufende Pipeline | Mittel 6,34 FPS, Hailo-Aufruf 43,03 ms, Verarbeitungszyklus 171,73 ms, Framealter beim Verarbeiten 25,04 ms |
| Kamera-Reconnect | Nur den RTSP-Socket von Kamera 1 im Zählprozess geschlossen; Fehler erkannt und nach etwa 4,3 Sekunden wieder gültige Frames. Kamera 2 blieb durchgehend ONLINE; Inferenz lief weiter |
| Einzelkamerabetrieb | Kamera 2 ohne Quelle: OFFLINE; Kamera 1 ONLINE bei etwa 25 FPS, Hailo-Inferenz läuft |
| GUI auf BOB | Zwei dekodierte, vollständig verpixelte Vorschauen, Vergrößerung per Bildklick und alle neun Navigationsseiten geprüft |
| Temperatur und Drosselung | 66,4 °C, `throttled=0x0` |
| Ressourcen | Zählprozess etwa 507 MB RSS und 281 % CPU über mehrere Kerne; GUI etwa 178 MB RSS. Zählprozess konstant 17 offene Deskriptoren im Messfenster |

Die Kameraadressen waren in den Altinstallationen widersprüchlich. Die aktuelle eigene LAN-Suche fand die beiden RTSP-Geräte; die gespeicherten Anmeldedaten funktionieren. Die falsche erste Kameraadresse wurde ausschließlich in der lokalen Deployment-Konfiguration korrigiert. WS-Discovery lieferte keine Multicast-Antworten. Der direkte ONVIF-Zugriff auf Kamera 1 funktionierte mit Authentifizierung; Kamera 2 lieferte keinen nutzbaren ONVIF-Zugriff. Das verhindert ihre RTSP-Nutzung nicht.

Beide offiziellen HEFs wurden durch den Installer heruntergeladen und per SHA-256 geprüft:

- YOLO26m: `f1435f7235c77b05736a5ab01b673cc156a95d85b5126aee7f7eb062ec2b2c66`.
- OSNet x1.0: `5c376b5e16cc42d8e5511aad649cc74b9503d4f44911a28ab157cbe899db1d39`.

## Behobene Fehler

1. Die Dienstvorprüfung widersprach dem Einzelkamerabetrieb und verlangte selbst bei pausiertem YOLO Modelldateien.
2. Die Startseite meldete Hailo trotz aktiver Inferenz als nicht bereit; sie verwendet jetzt `detector_active`.
3. Die Tagesbesucher-Datenbank war im Hauptthread erstellt, aber im Inferenzthread benutzt und geschlossen worden. Zugriffe werden mit einer reentranten Sperre serialisiert; Neustartpersistenz und parallele Registrierung sind getestet.
4. Manuelle schnelle Schalterwechsel erreichten das systemd-Startlimit. Explizite Benutzeraktionen setzen den Fehlerzähler zurück; automatische Absturzschleifen bleiben begrenzt.
5. Die Freeze-Erkennung klassifizierte geringfügig veränderte Livebilder als eingefroren: vorher 38/40 bzw. 39/40 Frames blockiert, danach 0/40 bei beiden Kameras. Freeze-Erkennung verlangt jetzt mehrere bitidentische Frames; Verdeckungs- und Helligkeitsprüfung bleiben bestehen.
6. Verbindungsaufbau bis zum ersten Reolink-Keyframe dauerte teils 6,6 Sekunden. Vorschau, Capture und Kameratest haben ein begrenztes 10-Sekunden-Zeitlimit; die Vorschau verwendet den Substream zur CPU-Entlastung.
7. Lesefehler zählten Wiederverbindungsversuche nicht korrekt. Der Reconnect-Zähler wird jetzt beim Stream-Lesefehler aktualisiert. Ein angeforderter Dienststopp während eines blockierenden Leseaufrufs wird nicht als Kamera-/Dekodierfehler protokolliert.
8. Tagesbesucher-Abfragen verwendeten bei benutzerdefinierten Datenbankpfaden einen anderen Ordner als der Zähldienst.
9. RTSP-Diagnose unterscheidet Port-Erreichbarkeit, erforderliche/abgelehnte/erfolgreiche Anmeldung und Streamprofil. Ein erreichbares Profil ist ausdrücklich noch kein Videonachweis. Bildblockaden werden im Status und auf der Startseite erklärt.
10. Die neu installierte OpenCV-5-Laufzeit erzeugte ONNX-Schemaregistrierungsfehler. Die Laufzeit ist auf OpenCV 4 begrenzt; auf BOB wurde 4.14.0 installiert und der gemeinsame Import von OpenCV, ONNX Runtime und Hailo geprüft.

## Tests und Grenzen der Abnahme

- Nicht-Hardware-Pytest auf BOB: **179 bestanden, 1 übersprungen**, Hardwaretests dabei separat abgewählt.
- Vorhandene Hardwaretests auf BOB: **8 bestanden**. Der Video-Gerätetest allein beweist keine USB-Kameras; der Kameranachweis hier beruht auf tatsächlich dekodierten RTSP-Bildern.
- Ruff gemäß CI-Auswahl `F,E9`, Python-Compile und Git-Diff-Prüfung bestanden. Globale zusätzliche Stilregeln sind nicht die CI-Abnahmeregeln dieses Projekts.
- Digital Twin: **11/11 bestanden**. Das sind synthetische Logiktests, keine Personen-Praxisabnahme.
- YOLO/Re-ID EIN/EIN, EIN/AUS, AUS/AUS und erneutes EIN/EIN am echten Dienst geprüft. Bei YOLO AUS: null Hailo-Aufrufe und unveränderte Zähler. Bei Re-ID AUS läuft YOLO weiter. Einzelkameramodus und Wiederaktivierung erfolgreich.
- Datenbank `PRAGMA integrity_check`: `ok`. Bestehende Aggregate bleiben bei Dienstneustarts erhalten; nichtleere Tagesprofile und Deduplizierung werden zusätzlich in temporären Testdatenbanken geprüft.
- Echte lokale API: Health 200, Zähler ohne Token 401, authentifizierte Counts/Runtime/Cameras/Version jeweils 200. Die API bleibt an die bestehende lokale Bind-Adresse gebunden; eine Android-Verbindung aus dem LAN ist damit nicht abgenommen.
- Android-UI-Praxisprüfung **NICHT VERIFIZIERT**: Kein Android-Gerät verbunden. Der vorhandene Emulator wurde über ARTEMIS gestartet, beendet sich jedoch wegen fehlendem Android-Emulator-Hypervisor-Treiber. Android-Unit-Tests/Build sind Bestandteil der GitHub-CI.
- Kontrollierte Personendurchgänge, korrekte Linienlage und Richtung, echte Ein-/Austrittsereignisse, kamerübergreifende Personen-Wiedererkennung und reale Tagesbesucher-Deduplizierung: **NICHT VERIFIZIERT**. Im Prüfzeitraum wurden keine kontrollierten Personenbewegungen bestätigt; die Zähler blieben null. Der OSNet-Bildausschnitt beweist die Hardwareberechnung, keine Personenidentität.
- Langzeit-Soak, seltene Deadlocks/Ressourcenlecks und echte Ende-zu-Ende-Kameralatenz: **NICHT VERIFIZIERT**. Die aufgeführten Framealter/Zykluszeiten sind keine Messung der Verzögerung vom Kamerasensor bis zur Anzeige.

Die Software ist auf BOB betriebsbereit. Eine vollständige Personen-Praxisabnahme und Android-Geräteabnahme sind weiterhin offen. `main` wurde nicht verändert.
