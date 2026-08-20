# Lokaler Projektassistent

## Ziel

Der Assistent soll direkt auf dem Raspberry Pi laufen, Fragen zum System beantworten, Diagnosewerte erklären, Projektdateien lokal durchsuchen und kleine Änderungen vorschlagen. Projektkontext, Konfigurationen und Diagnosedaten sollen standardmäßig nicht an externe KI-Dienste übertragen werden.

## Modellwahl

Standard ist **Gemma 4 E2B Instruct** in einer für `llama.cpp` geeigneten quantisierten Variante. Der Grund ist nicht maximale Modellgröße, sondern ein brauchbarer Kompromiss aus Antwortqualität, RAM-Bedarf und Reaktionszeit auf einem Raspberry Pi 5. Auf einem Pi mit 16 GB RAM kann optional **Gemma 4 E4B Instruct** verwendet werden. Größere Varianten sind für den Dauerbetrieb neben Video-Decoding, Hailo-Inferenz, Tracking und zwei Displays nicht der sichere Standard.

Der Assistent verwendet nicht das komplette Repository als einen riesigen Prompt. Stattdessen indexiert `ProjectKnowledgeBase` zulässige Textdateien und wählt zur Frage passende Ausschnitte aus. Das hält Speicherbedarf und Promptgröße begrenzt und verhindert, dass `data/`, `models/`, Logs oder Secrets in den Kontext gelangen.

## Laufzeit

Vorgesehen ist ein lokaler `llama.cpp`-Server auf `127.0.0.1:8080`. Beispiel:

```bash
llama-server \
  -m /opt/personenzaehler/models/gemma-4-e2b-it-q4.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 8192 \
  -t 4
```

Die exakte Quantisierung und Geschwindigkeit müssen auf der echten Pi-Hardware gemessen werden. Der Assistent darf die Hailo-Detektionspipeline nicht blockieren; CPU- und RAM-Limits werden deshalb im späteren systemd-Dienst getrennt gesetzt.

## Sicherheitsmodell

Der Agent ist bewusst kein autonomer Root-Agent.

- Lesen: nur freigegebene Projektdateitypen innerhalb des Repository-Verzeichnisses.
- Ausgeschlossen: `.git`, virtuelle Umgebungen, `models`, `data`, `logs`, Build-Artefakte und Cache-Verzeichnisse.
- Secrets werden vor dem Prompt redigiert.
- Schreiben: das Modell kann nur einen `ChangeProposal` erzeugen.
- Anwenden: nur durch eine explizite Benutzeraktion mit `confirmed=True`.
- Vor dem Schreiben wird der SHA-256-Stand der Zieldatei erneut geprüft. Damit kann ein alter Vorschlag keine zwischenzeitlich geänderte Datei überschreiben.
- Pfad-Traversal (`../`) und Änderungen außerhalb des Projekts werden blockiert.
- Potenzielle Secrets in vorgeschlagenem Inhalt werden blockiert.
- Binärdateien, Modelle und Datenbanken sind nicht schreibbar.

Damit bleibt die letzte Entscheidung beim Nutzer. Für Jugend forscht ist diese Trennung außerdem gut erklärbar: **LLM = Vorschlagskomponente, deterministische Schutzschicht = tatsächliche Änderungsberechtigung.**

## Internet und externe Coding-KI

Der Produktionsstandard bleibt lokal. Eine externe Coding-KI wird nicht automatisch kontaktiert. Falls später eine optionale Eskalation eingebaut wird, muss sie separat aktiviert werden, vor jeder Übertragung den anzuzeigenden Kontext offenlegen und Secrets sowie Laufzeit-/Personendaten entfernen. Für den aktuellen Stand ist diese Funktion bewusst nicht aktiv.

## Geplante Oberfläche

Die Benutzeroberfläche soll wie der Rest der Anwendung reduziert sein:

1. Chat-Eingabe unten, Antworten darüber.
2. Kontextanzeige über einen kleinen Button `Quellen`, damit sichtbar ist, welche Projektdateien verwendet wurden.
3. Änderungsvorschläge erscheinen als Karte mit Datei, Kurzbegründung und Diff.
4. Primäraktion `Änderung prüfen`; erst danach `Anwenden`.
5. Nach dem Anwenden automatisch passende Unit-Tests ausführen; bei Fehlern Rollback anbieten.
6. Keine technischen Rohfehler als erste Meldung. Zuerst verständlicher Status, Details aufklappbar.

## Noch zu testen

- reale Token/s auf Pi 5 mit 8 GB und 16 GB RAM
- Speicherverbrauch parallel zu Hailo/YOLO26m/OSNet
- thermisches Verhalten bei langer Unterhaltung
- Antwortqualität E2B gegen E4B
- korrekte Redaction bei ungewöhnlichen Secret-Formaten
- Konfliktverhalten bei gleichzeitig manueller Dateibearbeitung
- Recovery nach abgestürztem `llama-server`
