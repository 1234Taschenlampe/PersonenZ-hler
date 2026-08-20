# Digital-Twin-Emulator

Der Emulator testet den Besucherzähler ohne Raspberry Pi, Hailo-10H oder reale Kameras. Er ersetzt nur die physische Welt und die KI-Inferenz durch deterministische synthetische Daten; die eigentliche Zähl-, Tracking-, ReID- und Consensus-Logik aus dem Repository wird weiterverwendet.

## Was real getestet wird

- Tracker-Implementierung aus `src/visitor_counter/tracker.py`
- `GlobalIdentityManager` für kameraübergreifende IDs
- A/neutral/B-Hysterese und Richtungslogik aus `LineCrossingCounter`
- `DualCameraConsensus`
- globale Zählersemantik
- Ausfälle von Kamera, Router, Detektor und ReID
- mehrere Personen gleichzeitig
- Umkehr vor der Zähllinie
- gleiche bzw. sehr ähnliche ReID-Erscheinung
- Cross-Camera-ReID

## Was nur emuliert wird

- Kameraframes und RTSP-Transport
- YOLO26m-Detektionen
- Hailo-Laufzeit
- OSNet-Embeddings

Daher kann der Emulator logische Fehler sehr gut finden, aber nicht beweisen, dass YOLO26m reale Personen unter Gegenlicht korrekt erkennt oder wie viele FPS der echte Hailo-10H erreicht. Dafür bleiben spätere Hardwaretests notwendig.

## Headless starten

Alle Szenarien:

```bash
PYTHONPATH=src python -m visitor_counter.emulator
```

Ein bestimmtes Szenario:

```bash
PYTHONPATH=src python -m visitor_counter.emulator --scenario two_people
```

Alle verfügbaren Szenarien anzeigen:

```bash
PYTHONPATH=src python -m visitor_counter.emulator --list
```

Ein Exit-Code von `0` bedeutet, dass alle ausgewählten Szenarien bestanden wurden. Bei mindestens einem Fehler liefert der Emulator Exit-Code `1`; damit kann er später auch in CI verwendet werden.

## Grafische Oberfläche

```bash
PYTHONPATH=src python -m visitor_counter.emulator_gui
```

Die GUI zeigt beide Kamerarollen schematisch, erlaubt die Auswahl einzelner Szenarien oder den kompletten Testlauf und stellt PASS/FAIL sowie Soll-/Istwerte dar.

## Aktuelle Szenarien

- `normal_entry`
- `normal_exit`
- `turnaround`
- `two_people`
- `short_camera_dropout`
- `router_outage_no_false_count`
- `detector_outage_no_false_count`
- `same_person_cross_camera_reid`
- `similar_people_simultaneously`
- `reid_unavailable`
- `long_gap_reid_30s`

Einige Szenarien sind bewusst als harte Abnahmetests gedacht. Wenn ein Szenario fehlschlägt, soll nicht der Emulator passend gemacht werden; stattdessen ist zu prüfen, ob die Produktionslogik tatsächlich einen Fehler oder eine noch nicht umgesetzte Anforderung enthält.

## Wichtige Grenze

Der Emulator ist ein Digital Twin der Softwarelogik und kein Hailo-10H-Befehlssatz- oder Raspberry-Pi-Hardwareemulator. Exakte PCIe-/HailoRT-Latenzen, thermisches Throttling, WLAN-Funkstörungen, Decoderverhalten einer konkreten Kamera und reale YOLO-/OSNet-Genauigkeit können erst auf echter Hardware abschließend validiert werden.
