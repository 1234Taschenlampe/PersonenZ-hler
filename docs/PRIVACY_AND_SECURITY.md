# Datenschutz- und Sicherheitskonzept

Stand: August 2026. Dieses Dokument beschreibt technische Voreinstellungen und offene Betreiberpflichten; es ist keine Rechtsberatung und keine Zusage, dass ein konkreter Einsatz automatisch DSGVO-konform ist.

## Aktuelle Systemgrenzen

- YOLO26m erkennt ausschließlich Personen.
- ByteTrack hält lokale Track-IDs innerhalb einer Kamera.
- `global_person_id` bleibt als temporäre pseudonyme interne Kennung erhalten.
- OSNet ReID bleibt vorerst aktiv und dient nur der kameraübergreifenden Zuordnung bzw. Doppelzählungsvermeidung.
- Gesichtserkennung wird nicht unterstützt.
- Alter, Geschlecht, Emotion, Ethnie/Herkunft und vergleichbare Personenmerkmale werden nicht klassifiziert.
- Keine Namens-, Konto- oder Mitarbeiter-ID-Zuordnung.

## Sichere Voreinstellungen

- Inferenz findet lokal auf Raspberry Pi/Hailo statt. Es gibt keine Cloud-Telemetrie für Kameradaten.
- Die Kameraverarbeitung startet erst, wenn Rechtsgrundlage, Zweck, Verantwortlicher, Kontakt und sichtbarer Datenschutzhinweis dokumentiert sind.
- Bildvorschau und Remote-Video sind standardmäßig aus.
- Einzelbilder und Videos werden nicht dauerhaft gespeichert.
- OSNet-Embeddings bleiben ausschließlich im RAM und werden zusammen mit dem Identity-Cache verworfen.
- Die interne Person-ID wird nicht in normalen Logs veröffentlicht und nicht mit einer realen Identität verknüpft.
- Granulare Personenereignisse sind standardmäßig aus; die normale Datenbank speichert primär aggregierte Zähler.
- Ereignisspeicherung für Forschung erfordert getrennte Freigabe, Verschlüsselung und kurze Aufbewahrung.
- Die API bindet standardmäßig an `127.0.0.1`; Nicht-Loopback-Binding erfordert TLS und Authentifizierung.
- Netzwerk-Kamera-Zugangsdaten dürfen nicht ins Repository oder in Logs gelangen.

## ReID und Person-ID

Die aktuelle Identity-Konfiguration verwendet einen Cache von maximal 1800 Sekunden. Diese Dauer bleibt für die Forschungsphase bestehen, damit die Auswirkung auf Zählgenauigkeit und ReID zuverlässig gemessen werden kann. Sie muss vor einem konkreten Produktiveinsatz auf Erforderlichkeit geprüft werden.

Schutzregeln:

- keine persistente Embedding-Datenbank,
- keine dauerhafte Personenhistorie im Standardbetrieb,
- keine Gesichtsdaten,
- keine reale Identitätszuordnung,
- keine Verwendung von OSNet für andere Zwecke als Cross-Camera-Matching und Doppelzählungsvermeidung,
- keine Weitergabe der ReID-Daten an den lokalen Gemma-Agenten.

## Ausgeschlossene Analysefunktionen

Folgende Funktionen sind ausdrücklich nicht Bestandteil der Zielarchitektur:

- Face Recognition,
- Face Identification,
- Altersbestimmung,
- Geschlechtsbestimmung,
- Emotionserkennung,
- Ethnie-/Herkunftsklassifizierung,
- Gesundheits- oder Verhaltensprofiling.

Wenn eine dieser Funktionen später vorgeschlagen wird, muss sie als neue Datenschutzfunktion separat bewertet werden und darf nicht unbemerkt in den normalen Personenzähler einfließen.

## Datenbank und Logs

Standardmäßig werden nur Zähler- und Systemdaten benötigt. Personenbezogene Laufzeitdaten bleiben möglichst im Arbeitsspeicher.

Logs enthalten keine Bilder. Zugangsdaten, Tokens, Bounding-Boxes, Koordinaten, OSNet-Vektoren und interne Person-IDs sollen nicht in normalen Laufzeitlogs erscheinen. Die Logdateien werden mit restriktiven Dateirechten betrieben.

## Rollen und Funktionen

| Rolle | Zugriff |
| --- | --- |
| öffentlich | Minimaler Health-Check und Datenschutzhinweis |
| `viewer` | Status, Zähler, Kamerazustand, WebSocket |
| `operator` | zusätzlich Telemetrie und bewusst freigegebene Diagnosefunktionen |
| `admin` | zusätzlich Datenschutzexport/-löschung für gespeicherte Daten |

## Inbetriebnahme

1. Zweck, Erforderlichkeit, Erfassungsbereich und mögliche mildere Mittel dokumentieren.
2. Rechtsgrundlage und Interessenabwägung bzw. andere Voraussetzungen prüfen.
3. Kameras auf den kleinstmöglichen notwendigen Bereich begrenzen.
4. Datenschutzhinweis vor dem Aufnahmebereich anbringen.
5. `config/config.yaml` ausfüllen: `legal_basis`, `purpose`, `controller_name`, `controller_contact`, `privacy_notice_acknowledged` und Zeitpunkt.
6. Echte Kamerazugangsdaten ausschließlich lokal eintragen.
7. Remotezugriff nur bei Bedarf und nur mit Authentifizierung/TLS aktivieren.
8. Löschverhalten, Kameraausfälle, ReID-Cache, Logs und Berechtigungen vor Livebetrieb testen.

## Lokaler Gemma-Agent

Der lokale Projektassistent erhält Quellcode, Dokumentation und technische Diagnosewerte, aber keine Rohframes, Personencrops, OSNet-Embeddings oder personenbezogene Ereignisdaten. `data/`, `logs/` und `models/` sind aus seinem Projekt-RAG ausgeschlossen.

## Lizenz- und Startschutz

Der Startschutz ist vom Datenschutzsystem getrennt. Die Produktionssoftware kann eine signierte lokale Lizenz plus eine passende signierte GitHub-Freischaltung verlangen. Details stehen in `docs/LICENSE_SYSTEM.md`. Die Onlineprüfung erfolgt ausschließlich per HTTPS.

## DSGVO-Bezug

Die technischen Voreinstellungen unterstützen insbesondere Datenminimierung, Speicherbegrenzung, Integrität/Vertraulichkeit und Datenschutz durch Technikgestaltung. Die konkrete Rechtmäßigkeit kann die Software nicht selbst feststellen.

Für den aktuellen Stand werden als maßgebliche Quellen insbesondere herangezogen:

- DSGVO, insbesondere Art. 4, 5, 6, 9, 13, 25, 32 und 35,
- EDSA/EDPB-Leitlinien 3/2019 zur Verarbeitung personenbezogener Daten durch Videogeräte,
- Orientierungshilfen der deutschen Datenschutzkonferenz zu Videoüberwachung, KI und technischen/organisatorischen Maßnahmen.

## Verbleibende Risiken

- OSNet kann rechtlich sensibler sein als reine Detection und Tracking; die konkrete Einordnung muss für den Einsatzort geprüft werden.
- Eine 30-minütige interne ID ist für die Forschung technisch gewünscht, muss aber später auf tatsächliche Erforderlichkeit geprüft werden.
- RAM, Prozessspeicher und Kameratreiber enthalten kurzfristig Rohbilder.
- Ein kompromittiertes Betriebssystem kann auf Laufzeitdaten zugreifen.
- Zählergebnisse können falsch sein und dürfen nicht allein Grundlage personenbezogener oder sicherheitskritischer Entscheidungen sein.
- Eine DSFA oder weitere organisatorische Pflichten können je nach Einsatz erforderlich sein.
