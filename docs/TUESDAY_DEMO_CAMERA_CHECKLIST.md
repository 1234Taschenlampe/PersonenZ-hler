# Dienstag: Vorführung mit zwei Reolink-Kameras und echtem YOLO26m

Die Kamera-FPS allein sind kein Beweis für funktionierende KI-Auswertung.
Der Raspberry Pi empfängt zwei RTSP-Hauptstreams parallel; der Hailo-10H
führt YOLO26m auf abwechselnd den **jeweils neuesten Frames** aus.
Jeder Frame wird in seiner nativen Stream-Auflösung erfasst und erst im
Modell-Preprocessing auf 640×640 letterboxed. Die lokale Vorschau wird
höchstens auf 1920×1080 unter Erhalt des Sichtfelds skaliert.

## Einrichten und überprüfen

1. Nach dem GitHub-Update den Zähldienst neu starten. Bestehende IPs,
   RTSP-Zugangsdaten, LAN-Konfiguration und gespeicherte Zähler bleiben erhalten.
2. **Kameras**: Beide Reolink-Quellen auf den RTSP-Hauptstream
   (`Preview_01_main`) umstellen; einzeln Bildübertragung testen.
   Alte gespeicherte `_sub`-URLs werden nicht still geändert.
3. **Kameras**: Bei beiden Quellen **Am Bildrand nach bestätigtem
   Verlassen** wählen und speichern. Diese Einstellung bleibt bei älteren
   Installationen ausdrücklich erhalten, bis sie umgestellt wird.
4. Unter **Einstellungen** YOLO26m und OSNet ReID eingeschaltet lassen.
   Die KI läuft auch dann weiter, wenn die Vorschau deaktiviert ist.
5. **Übersicht**: Die lokale Live-Vorschau aktivieren. Dadurch werden die
   Bilder **unverpixelt** im flüchtigen Arbeitsspeicher /dev/shm angezeigt,
   inklusive grüner Bounding Boxes, Track-IDs und beschrifteter Randbereiche.
   Keine Bildaufzeichnung auf persistenten Datenträgern.
6. **Kameras / Übersicht**: Für jede Kamera `ONLINE`, reale Auflösung,
   Empfangs-FPS, `ai_fps > 0`, `inference_status=active`, Personendetektionen
   und bestätigte Tracks beobachten. Das Hailo-Modell und die HEF/ONNX-Ausgabe
   müssen auf dem echten Pi geprüft werden.

## So wird am Bildrand gezählt

- Der alte Mittelstrich ist im neuen **Bildrandmodus** kein Zählziel
  mehr. Seine Richtung bestimmt nur, welche gegenüberliegenden Ränder
  als Eintritt beziehungsweise Austritt gelten.
- Für jeden eindeutig verfolgten Track gilt:
  **mehrere echte Beobachtungen** + **ausreichende Bewegung zur passenden
  Bildgrenze** + **zuletzt am Rand** + **anschließendes bestätigtes
  Verschwinden** = ein Ereignis (+1 oder -1).
- Aussetzer oder Verdeckung mitten im Bild, Stillstand am Rand oder
  fehlende Track-Bestätigung lösen keine Zählung aus.
- Die Auslösung erfolgt nach `disappearance_frames` verarbeiteten
  Kameraframes (neue Standardeinstellung: 4). Die Geschwindigkeit hängt
  damit von der tatsächlich erzielten **KI-FPS pro Kamera** ab.
- Beide Kameras zählen unabhängig; Doppelzählungsunterdrückung und OSNet
  wirken auf die globale Besucherzahl.

## Python 3.15 auf dem Pi

Python 3.15.0 wurde am 9. Oktober 2026 freigegeben.
**Die vorhandene, funktionierende Pi-Laufzeit NICHT automatisch ersetzen.**
HailoRT-5-Bindings, OpenCV, PySide6 und ONNX Runtime bestehen zu einem
wesentlichen Teil aus nativen Python-Erweiterungen; ein Interpreterupgrade
kann diese Pakete inkompatibel machen. Der Installer verwendet daher
weiterhin das vorhandene `python3` mit `--system-site-packages`.
`pyproject.toml` erlaubt neuere Python-Versionen, sobald
die komplette Hailo-Pipeline auf dem Zielgerät geprüft wurde.
Die beschleunigte YOLO-Inferenz läuft bereits auf dem Hailo-10H,
nicht im Python-Interpreter; ein Python-Upgrade garantiert
daher keine höhere KI-FPS.

## Technische und datenschutzbezogene Grenze

Keine Videoaufnahme und kein Video-Upload. Raw-Preview ist nur lokal
und ausschließlich auf RAM-Dateisystem erlaubt; der remote erreichbare
Videostream erlaubt **keine** unverpixelten Bilder. Datenbankverschlüsselung
für gegebenenfalls gespeicherte Ereignisse ist ein eigenständiger Schutz
und bleibt eingeschaltet. Beim Einsatz mit Personen außerhalb privater
Tests sind rechtliche und organisatorische Anforderungen unabhängig von
der verwendeten Technik zu berücksichtigen.

## Abnahme am echten Gerät

- Person steht im Bild: mindestens eine YOLO-Erkennung und ein Track,
  **kein** künstlicher Eintritt.
- Person verlässt Bild zur als **IN** markierten Kante: einmal +1;
  Person geht zur **OUT** markierten Gegenkante: einmal -1.
- Bei zwei gleichzeitig aktiven Kameras muss jede Quelle eigene
  Frames/Detektionen/Track-IDs liefern.
- Bei nur einer erreichbaren Kamera muss deren Zählung weiterlaufen.
- Wenn ein Rand-Exit nicht zählt: letzte Box am Rand? gerichtete Bewegung?
  bestätigter Track? genug KI-Frames nach dem Verlassen?
  Consensus-Ereignis verworfen? KI-FPS / Hailo-Status prüfen.

**Nur CI-Tests im Repository sind kein Hardware-Abnahmetest.**
