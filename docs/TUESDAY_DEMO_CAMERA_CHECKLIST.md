# Dienstag: HD-Kamera- und KI-Zähl-Demonstration

**Reales Verhalten auf dem Pi prüfen.** GitHub CI simuliert die Bildpipeline,
aber beweist keine funktionsfähige Reolink-RTSP-/Hailo-Verbindung.

## Nach dem Update

1. Programm aktualisieren und den **Zähldienst** neu starten. Vorhandene
   Kamera-IP-Adressen, Zugangsdaten, Datenbanken und LAN-Konfiguration behalten.
2. Unter **Kameras** beide Reolink-Quellen auf **Hauptstream** (`Preview_01_main`)
   stellen, einzeln Video-Frame testen und speichern. Aktuell konfigurierte
   `_sub`-Streams bleiben unverändert, bis sie bewusst umgestellt werden.
3. Unter **Einstellungen** prüfen, dass **YOLO26m aktiviert** ist. Danach
   **Übersicht** > **Anonymisierte Livebilder** aktivieren.
4. Unter **Datenschutz** die lokale Darstellung wählen: Standard
   **gesamtes Bild verpixeln** oder für eine abgesprochene lokale
   Demonstration **Personen verpixeln, Umgebung scharf**. Dieser Modus
   ist bei Remote-Livebild nicht zulässig. Die Anonymisierung schützt
   nur erkannte Personen, nicht zuverlässig Gesichter auf Plakaten etc.;
   in öffentlichen Umgebungen eine geeignete Rechtsgrundlage beachten.
5. Im vergrößerten Livebild zuerst **ganzen Bildausschnitt** kontrollieren,
   dann optional **Originalgröße (1:1)** wählen. Der GUI-Export ist
   auf max. 1920×1080 begrenzt (Seitenverhältnis bleibt erhalten);
   der KI-Pfad erhält weiterhin den dekodierten Kameraframe und
   verwendet das vom HEF geforderte 640×640-Letterbox-Format.

## Verbindliche Abnahmekriterien

- Für **jede** Kamera: `ONLINE`, tatsächliche Streamauflösung, Empfangs-FPS,
  Frames empfangen, Frames durch KI verarbeitet, `inference_status=active`.
- Auf eine stehende Person ausrichten: `detections >= 1` und
  `confirmed_tracks >= 1`, visuelle Bounding Box und Track-ID.
  Ein Stehen ohne Linienüberquerung **darf keinen Eintritt zählen**.
- Eine Person bewegt sich nacheinander vollständig über die gezeichnete
  Zähllinie in beide Richtungen: jeweils genau ein richtiger Ereigniszähler
  ändert sich. Zähllinie muss exakt mit der Darstellung übereinstimmen.
- Beide Kameras parallel verbinden: Auflösungen, KI-FPS, bestätigte Tracks
  und Durchfluss getrennt kontrollieren. Bei nur einer Online-Kamera muss
  deren KI weiterlaufen. CPU-Auslastung und Temperatur prüfen.
- Kein Aufzeichnen von Bildern; lokale Vorschaudateien nur im flüchtigen
  RAM-Verzeichnis. Remote-Video bleibt standardmäßig deaktiviert.

**Bei Fehlern**: Unterschied zwischen fehlenden Kameraframes, deaktivierter KI,
0 YOLO-Detektionen, gefilterten Detektionen, noch nicht bestätigten Tracks,
falscher Zähllinie, ReID und unterdrückten Duplikaten unterscheiden.
Nicht allein aus einem flüssigen Livebild auf funktionierende KI schließen.
