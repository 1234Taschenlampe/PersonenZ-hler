# Benutzerhandbuch

## Erster Start

Der Assistent führt durch Systeminformationen, Hailo/Modelle, zwei Kameraquellen, konfigurierbare Kamerarollen, Datenschutzangaben, lokale API und Lizenzstatus. Offene Punkte werden am Ende als konkrete Liste gezeigt. Speichern ist möglich, aber der Produktionsdienst bleibt fail-closed, bis Lizenz, Datenschutz, Kameras, Hailo und Modelle bereit sind.

## Übersicht

Die Übersicht trennt aktuelle Belegung, eindeutige Besucher des Tages, Ein-/Austritte, Durchfluss, unterdrückte Doppelzählungen, unsichere Ereignisse und Fehlrichtungen. Statusfelder zeigen Hailo, Kameras, Datenbank, Dienst, Lizenz und Datenschutz.

## Kameras

**Kameras suchen** erkennt echte V4L2-Videoquellen und bevorzugt stabile `/dev/v4l/...`-Pfade. RTSP/RTSPS/HTTP(S)-Quellen können eingetragen werden. Für jede Kamera sind Anzeigename, Eingang-/Ausgangsrolle und erwartete A→B-/B→A-Richtungen konfigurierbar. `none` markiert einen Übergang als Fehlrichtung. **Verbindung testen** läuft im Hintergrund und friert die GUI nicht ein.

Kameravorschauen sind standardmäßig aus. Eine aktivierte lokale Vorschau wird gemäß der Privacy-Konfiguration anonymisiert; Remote-Livebild bleibt separat und standardmäßig deaktiviert.

## KI & Hardware

Hier werden YOLO26m- und OSNet-HEFs importiert. **Hardwareprüfung starten** sammelt Betriebssystem, Architektur, Runtime, HailoRT, Kamera-, Modell-, CPU-, RAM- und Temperaturinformationen. Ein fehlender Hailo-10H oder ein falsches/fehlendes Modell wird sichtbar als Fehler dargestellt.

## Ereignisse und Verlauf

Granulare Ereignisse sind aus Datenschutzgründen standardmäßig aus. Wenn der Betreiber sie explizit mit einem Verschlüsselungsschlüssel aktiviert, zeigt die Ereignisseite Passagen, Unsicherheit und Fehlrichtungen; Retention löscht alte Datensätze automatisch. Der Verlauf verwendet aggregierte Werte.

## System und Android

Die Systemseite startet, stoppt und startet die eng begrenzten Hintergrunddienste über PolicyKit neu. Außerdem zeigt sie Datenbank und API-Endpunkt, liest Journal-Logs und erstellt ein redigiertes Diagnose-ZIP.

Für Android:

1. Unter **Einstellungen** ein Zertifikat und den zugehörigen privaten TLS-Schlüssel importieren.
2. API-Bindung auf eine passende LAN-Adresse oder `0.0.0.0` setzen; außerhalb Loopback akzeptiert die Konfiguration nur Authentifizierung plus TLS.
3. Den API-Dienst auf der Systemseite neu starten.
4. **Android-Pairing exportieren** wählen, den Systemdialog bestätigen und die Datei geschützt auf das Mobilgerät übertragen.
5. URL und Viewer-Token in der Android-App übernehmen und die Pairing-Datei danach löschen.

Die Pairing-Datei enthält nur den Viewer-Token, niemals Operator-/Admin-Token oder private Schlüssel. Der TLS-Zertifikatfingerabdruck dient der kontrollierten Gegenprüfung.

## Datenschutz & Sicherheit

Dieser Bereich dokumentiert Verantwortlichen, Kontakt, Zweck, geprüfte Rechtsgrundlage und sichtbaren Datenschutzhinweis. Lokale Vorschau, Remote-Livebild, verschlüsselte Ereignisspeicherung und Retention sind explizite Optionen. **Personenbezogene Daten löschen** entfernt granulare Ereignisse und pseudonyme Sitzungen; aggregierte Zähler bleiben standardmäßig erhalten.

Eine signierte Lizenz kann importiert und ihr Status eingesehen werden. Die GUI bleibt bei fehlender Lizenz für Einrichtung und Diagnose nutzbar.

## Einstellungen

Detektions-/Re-ID-Schwelle, Anwesenheits-Timeout, API-Aktivierung, Bindung, Port und TLS-Dateien sind grafisch änderbar. Unsichere Remote-Konfigurationen, externe Telemetrie und produktive CPU-/Dummy-Fallbacks werden von der Validierung abgewiesen.

## Häufige Meldungen

- **KI-Beschleuniger nicht bereit:** HailoRT, Hailo-10H, Firmware oder HEF fehlt; Hardwareprüfung öffnen.
- **Kamera nicht erreichbar:** Quelle, Strom, Netzwerk/V4L2-Pfad und Rollen prüfen.
- **Lizenz nicht vorhanden/ungültig:** signierte Lizenz importieren; Gerätefingerabdruck vergleichen.
- **Datenschutzkonfiguration unvollständig:** markierte Betreiberfelder und sichtbaren Hinweis vervollständigen.
- **Service konnte nicht gestartet werden:** Logs auf der Systemseite aktualisieren und Diagnosepaket exportieren.
- **Pairing nicht möglich:** API muss remote, authentifiziert und TLS-geschützt konfiguriert sein.

## Diagnoseexport

Das ZIP enthält Systembericht, redigierte Konfiguration und begrenzte Log-Auszüge. Datenbank, Bilder, Videos, API-Tokens, Passwörter und private Schlüssel werden nicht aufgenommen. Bekannte URL-Credentials und Bearer-Tokens werden automatisch ersetzt.
