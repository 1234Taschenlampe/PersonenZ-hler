# Architektur V2 – Zwei WLAN-Kameras, Hailo-10H, YOLO26m und OSNet ReID

## Zielhardware

- Raspberry Pi 5 als zentraler Server
- Hailo-10H als KI-Beschleuniger
- zwei WLAN/IP-Kameras im lokalen Router-Netz
- eigener Router bzw. dediziertes LAN/WLAN für Kameras, Pi und optionale Clients
- zwei lokale Displays am Raspberry Pi

Der Raspberry Pi sollte nach Möglichkeit per Ethernet am eigenen Router hängen. Die Kameras können per WLAN verbunden sein. Dadurch liegt nur die Kamerastrecke auf Funk und die Serveranbindung bleibt stabil.

## Datenfluss

```text
WLAN Kamera 1 ─┐
               ├─ RTSP/HTTP Capture ─ LatestFrameHub ─ YOLO26m/Hailo ─ ByteTrack
WLAN Kamera 2 ─┘                                                    │
                                                                    v
                                                               OSNet ReID
                                                                    │
                                                                    v
                                                        GlobalIdentityManager
                                                                    │
                                 ┌──────────────────────────────────┴─────────────────────────────────┐
                                 v                                                                    v
                        3-Zonen-Hysterese                                                     Sichtbarkeitsstatus
                         A / neutral / B                                                      (nur Telemetrie)
                                 │
                                 v
                        DualCameraConsensus
                                 │
                                 v
                         Eintritt / Austritt
                                 │
                    ┌────────────┴─────────────┐
                    v                          v
              SQLite Aggregate          live_status.json
                                               │
                              ┌────────────────┼─────────────────┐
                              v                v                 v
                         Status API       Display 1          Display 2
                                         Belegung           Systemstatus
```

## Kamerapipeline

`CameraCapture` unterstützt weiterhin lokale V4L2-Kameras und zusätzlich RTSP/RTSPS/HTTP/HTTPS. Netzwerkquellen werden über OpenCV/FFmpeg geöffnet. Der systemd-Dienst setzt für RTSP TCP als Transport. Bei Open- oder Decodefehlern wechselt die Kamera in `RECONNECTING`, zählt Fehler und versucht die Verbindung erneut aufzubauen.

Pro Kamera existiert im `LatestFrameHub` nur ein Slot. Wenn die Verarbeitung langsamer als die Kamera ist, ersetzt ein neuer Frame den alten. Es wird kein Video-Backlog aufgebaut. Für einen Echtzeit-Personenzähler ist ein aktuelles Bild wichtiger als das nachträgliche Verarbeiten jedes Frames.

## Detektion und Tracking

Produktiver Detektor bleibt das freigegebene YOLO26m COCO Detection HEF für Hailo-10H. Es wird ausschließlich COCO-Klasse 0 (`person`) verarbeitet. Pose ist kein Fallback und wird für die Zählung nicht benötigt.

ByteTrack erzeugt lokale Track-IDs pro Kamera. Die Track-IDs selbst sind nicht kameraübergreifend stabil.

## OSNet ReID

OSNet x1.0 erzeugt für bestätigte Personentracks normalisierte Appearance-Embeddings. Die Inferenz läuft ebenfalls über Hailo. Detection und ReID verwenden eine geteilte Hailo-Gruppe und Round-Robin Scheduling.

Für kameraübergreifende Zuordnung ist OSNet das primäre Signal. Die aktuelle Bewertung verwendet:

- 60 % OSNet-Cosinusähnlichkeit
- 20 % zeitliche Plausibilität
- 15 % Bounding-Box-Form/-Größe
- 5 % normalisierte Bildposition

Fehlt auf einer Seite ein Embedding, darf Geometrie allein den normalen ReID-Schwellwert nicht erreichen. Damit soll verhindert werden, dass zwei ähnlich große Personen nur wegen ähnlicher Position und zeitlicher Nähe zusammengeführt werden.

Der ReID-Cache ist standardmäßig auf 1800 Sekunden begrenzt. Embeddings werden nicht als Bilddateien gespeichert.

## Zählentscheidung

Die produktive Belegungszahl wird nicht aus "Person sichtbar / Person verschwunden" abgeleitet. Sichtbarkeit ist nur Telemetrie.

Ein Track muss die Hysteresezone stabil durchlaufen. Die bestehende Linienlogik bildet drei Zustände:

```text
A  ->  neutral  ->  B
B  ->  neutral  ->  A
```

Nur eine gültige Richtung der jeweiligen Kamera erzeugt ein Crossing-Event. Track-Bestätigung, Mindesthistorie, Mindestkonfidenz, Mindest-Bounding-Box-Größe und Cooldown werden vor dem Event geprüft.

Anschließend prüft `DualCameraConsensus`, ob ein Ereignis zur zweiten Kamera gehört bzw. ein Duplikat oder unsicherer Fall ist. Nur bestätigte, nicht unsichere Crossing-Entscheidungen ändern `entered`, `exited` und `inside`.

## Kameraausfälle

Die Laufzeitdaten unterscheiden:

- `CONNECTING`
- `ONLINE`
- `RECONNECTING`
- `OFFLINE`

Zusätzlich werden unter anderem `actual_fps`, `last_frame_time`, `seconds_since_last_frame`, `reconnect_count`, `dropped_frames` und `decode_errors` veröffentlicht.

Ein einzelner Kameraausfall beendet den Capture-Thread nicht dauerhaft. Der Inferenzdienst bleibt aktiv und verarbeitet die andere Kamera weiter. Ereignisse während eines vollständigen Ausfalls können naturgemäß nicht rekonstruiert werden.

## Zwei Displays

`python -m visitor_counter.display_dashboard` öffnet zwei datenschutzarme Vollbildfenster:

1. Display 1: aktuelle Belegung sowie Ein-/Austritte
2. Display 2: Kamera-, Hailo-, ReID-, Latenz- und Queue-Status

Die Anzeige liest lokal `data/live_status.json`. Dafür muss weder Videomaterial noch ein Netzwerk-API-Endpunkt an die Displays übertragen werden. Sind nur ein Bildschirm bzw. nur ein erkannter Desktop-Screen vorhanden, werden beide Fenster auf dem verfügbaren Screen erzeugt; für den echten Zwei-Monitor-Betrieb muss die Raspberry-Pi-Desktopumgebung beide Ausgänge als getrennte Screens melden.

## Datenschutz und Speicherung

Die vorhandenen Privacy-Gates bleiben erhalten. Der produktive Dienst startet nicht, solange die erforderlichen Datenschutz-Konfigurationsfelder fehlen.

Standardmäßig werden keine Videoframes persistiert und persönliche Einzelereignisse sind deaktiviert. Die aggregierten Zähler werden in SQLite gespeichert. Netzwerk-Kamera-Zugangsdaten dürfen nicht in Beispiel- oder Dokumentationsdateien eingecheckt werden.

## Noch vor Produktivbetrieb zu konfigurieren

1. Die echten RTSP/HTTP-URLs der beiden WLAN-Kameras in `config/config.yaml` eintragen. `config/config.wlan.example.yaml` enthält nur Platzhalter.
2. Kamera-1-/Kamera-2-Rolle und Durchlaufrichtung vor Ort prüfen.
3. Zähllinie und Hysterese an den realen Bildausschnitt anpassen.
4. Datenschutz-Freigabefelder ausfüllen.
5. Vorhandensein und Hailo-Lesbarkeit beider HEFs prüfen.
6. Mit realen Durchgängen testen: einzeln, zwei Personen nebeneinander, direkt hintereinander, Umkehr, Verdeckung, ähnliche Kleidung, Kamera-Reconnect und Router-Neustart.
7. Erst nach diesen Hardwaretests den Branch in `main` übernehmen.
