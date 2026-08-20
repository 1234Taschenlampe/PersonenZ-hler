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

## Tageszählungs-spezifische sichere Voreinstellungen

Stand: 18. August 2026. Dieses Dokument beschreibt technische Voreinstellungen und offene Betreiberpflichten; es ist keine Rechtsberatung und keine Zusage, dass ein konkreter Einsatz automatisch DSGVO-konform ist.

## Sichere Voreinstellungen

- Inferenz findet lokal auf Raspberry Pi/Hailo statt. Der Laufzeitcode hat keine Cloud-, Analytics- oder Telemetrie-Integration.
- `privacy.enabled`, `local_processing_only` und der systemd-Netzwerk-Namespace sind aktiv; externe Telemetrie ist unzulaessig.
- Die Kameraverarbeitung startet erst, wenn Rechtsgrundlage, Zweck, Verantwortlicher, Kontakt, sichtbarer Hinweis und Zeitpunkt der Betreiberbestaetigung dokumentiert sind.
- Bildvorschau und Remote-Video sind aus. Werden sie bewusst aktiviert, ist fuer Remote-Video Vollbild-Verpixelung vorgeschrieben. Dadurch werden auch Kennzeichen und Gesichter verdeckt, obwohl das Person-only-Modell diese nicht separat erkennt.
- Fuer den eindeutigen Tagesbesucherzaehler ist OSNet-Re-ID aktiviert. Die daraus abgeleiteten Merkmalsvektoren werden ausschliesslich lokal fuer den Vergleich innerhalb des aktiven Kalendertages verwendet. Mit vorhandenem `VISITOR_COUNTER_DATA_KEY` werden Tagesprofile verschluesselt in `data/daily_unique.sqlite3` gespeichert, damit Neustarts nicht automatisch zu Doppelzaehlungen fuehren. Beim Tageswechsel werden Profile des Vortags geloescht. Ohne Schluessel arbeitet die Tagesdeduplizierung nur im RAM und wird in der GUI als eingeschraenkt markiert.
- Einzelbilder/Videos werden nicht dauerhaft gespeichert. Kurzlebige Streambilder liegen unter Linux bevorzugt in `/dev/shm`, tragen Modus `0600`, gelten maximal drei Sekunden und werden beim Beenden geloescht.
- Granulare Personenereignisse sind aus. Es bleiben nur aggregierte Zaehler. Werden Ereignisse aktiviert, verlangt die Anwendung einen externen Fernet-Schluessel, verschluesselt Textfelder und ersetzt Personen-/Track-IDs durch schluesselgebundene Pseudonyme.
- Ereignisaufbewahrung ist auf 24 Stunden voreingestellt und auf maximal sieben Tage begrenzt. Beim Start und alle fuenf Minuten werden abgelaufene Datensaetze geloescht; SQLite `secure_delete` und WAL-Truncation sind aktiv.
- Logs enthalten keine Bilder. Ein Filter entfernt Track-/Personen-IDs, Bounding-Boxes, Bildkoordinaten und Secrets. Rotation, kurze Dateiaufbewahrung und Dateirechte `0600` sind aktiv.
- Die API bindet an `127.0.0.1`, nutzt keine CORS-Wildcard und fordert getrennte Tokens fuer `viewer`, `operator` und `admin`. Nicht-Loopback-Binding wird ohne TLS plus Authentifizierung verweigert.
- Android verweigert Klartextverkehr, akzeptiert nur HTTPS zu lokalen/privaten Zielen, speichert das Token verschluesselt und sperrt Screenshots/Recent-Task-Vorschauen.
- SSH-Helfer akzeptieren keine unbekannten Hostschluessel und bevorzugen Agent/Schluesseldatei. Passwortauthentifizierung muss explizit freigeschaltet werden.

## Zaehler und Datenminimierung

Die produktive Statistik trennt vier Zwecke:

- `inside`: aktuelle Belegung; +1 bei bestaetigtem Eintritt, -1 bei bestaetigtem Austritt.
- `daily_unique`: eindeutige Besucher des aktuellen lokalen Kalendertages; dieselbe Re-ID soll nur einmal zaehlen.
- `entered` / `exited`: persistente bestaetigte Passagen nach Richtung.
- `throughput`: abgeleitet als `entered + exited`.

Die aktuelle Belegung wird nicht aus bloss sichtbaren Personen abgeleitet. Sichtbarkeit bleibt ein Diagnosewert. Dadurch werden kurze Verdeckungen nicht als Austritt gewertet.

## Re-ID und Tagesprofile

Der eindeutige Tageszaehler benoetigt eine Wiedererkennung ueber mehrere Eintritte desselben Tages. Dazu werden normalisierte OSNet-Merkmalsvektoren verglichen. Es werden keine Namen zugeordnet und keine Gesichtserkennung ausgefuehrt. Trotzdem handelt es sich um eine deutlich eingriffsintensivere Verarbeitung als reine Personendetektion. Der konkrete Betreiber muss vor Aktivierung bzw. Livebetrieb insbesondere Zweck, Erforderlichkeit, Rechtsgrundlage, Transparenz und die Notwendigkeit einer Datenschutz-Folgenabschaetzung pruefen.

Technische Grenzen:

- Profile gelten nur fuer den lokalen Kalendertag.
- Alte Profile werden bei Tageswechsel aus der Tagesdatenbank entfernt.
- Persistente Tagesprofile sind mit Fernet verschluesselt; der Schluessel liegt ausserhalb des Repositories.
- Ohne Schluessel erfolgt nur RAM-basierte Deduplizierung und ein Neustart kann zu erneuter Zaehlung fuehren.
- Aehnlich aussehende Personen koennen falsch zusammengefuehrt werden; dieselbe Person kann bei stark veraendertem Erscheinungsbild als neu gelten. Der Tageszaehler ist daher eine statistische Schaetzung und keine Identitaetsfeststellung.

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

Für aktivierte Tages-Re-ID gelten zusätzlich:

1. Zweck, Erforderlichkeit, Erfassungsbereich und mildere Mittel dokumentieren. Kameras auf den kleinstmoeglichen Bereich begrenzen und oeffentliche Wege/Nachbarbereiche maskieren.
2. Rechtsgrundlage und Interessenabwaegung bzw. andere Voraussetzungen pruefen. Fuer den Tages-Re-ID-Zweck ist eine gesonderte Pruefung erforderlich; er darf nicht stillschweigend unter den Zweck einer einfachen Belegungszaehlung subsumiert werden.
3. Das Muster `PRIVACY_NOTICE_TEMPLATE.md` ausfuellen und den Hinweis vor dem Aufnahmebereich anbringen. Die Information muss den Re-ID-/Tageszaehlzweck abbilden, wenn dieser aktiv ist.
4. `config/config.yaml` ausfuellen: `legal_basis`, `purpose`, `controller_name`, `controller_contact`, `privacy_notice_acknowledged: true` und einen ISO-8601-Zeitpunkt setzen.
5. Secrets ausserhalb des Repositories erstellen. Der Linux-Installer nutzt standardmaessig `~/.config/personenzaehler/api.env`.

## Lokaler Gemma-Agent

Der lokale Projektassistent erhält Quellcode, Dokumentation und technische Diagnosewerte, aber keine Rohframes, Personencrops, OSNet-Embeddings oder personenbezogene Ereignisdaten. `data/`, `logs/` und `models/` sind aus seinem Projekt-RAG ausgeschlossen.

6. Fuer mobilen Zugriff ein Zertifikat fuer den lokalen Hostnamen aus einer vom Android-Geraet vertrauten CA verwenden, Zertifikat/Key in `api.tls_certificate` und `api.tls_private_key` eintragen und erst dann `api.bind_host` auf eine private Adresse setzen. Der Private Key muss `0600` bleiben.
7. Falls kein Remotezugriff erforderlich ist, API auf Loopback und Video/mDNS deaktiviert lassen.
8. Zugriffsrechte, Loeschung, Wiederherstellung, Hinweisbeschilderung, Tageswechsel, Re-ID-Deduplizierung und Kameramasken vor Livebetrieb testen; Pruefung regelmaessig wiederholen.

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

## Trainingsdaten

Trainingsbilder sind getrennt vom Laufzeitbetrieb zu behandeln. Die Capture/Extract/Hard-Negative-Skripte verlangen eine externe, befristete JSON-Freigabe mit `approved`, `purpose`, `legal_basis`, `controller` und `expires_at`, einen expliziten Ausgabeordner und private Dateirechte. Rohdaten gehoeren auf ein verschluesseltes, zugriffsbeschraenktes Volume und duerfen nicht in Git, Cloud-Synchronisation oder Backups gelangen. Nach Ablauf sind Bilder, Labels, abgeleitete Crops und Backups gemeinsam zu loeschen.

## DSGVO-Bezug

Die Voreinstellungen unterstuetzen Datenminimierung, Speicherbegrenzung, Integritaet/Vertraulichkeit und Rechenschaftspflicht nach Art. 5 sowie Datenschutz durch Technikgestaltung nach Art. 25 und angemessene Sicherheit nach Art. 32. Transparenz- und Betroffenenpflichten bleiben organisatorisch zu erfuellen. Fuer Re-ID muss zusaetzlich geprueft werden, ob die konkrete Verarbeitung Merkmale zur eindeutigen Identifizierung im Sinne der biometrischen Definition der DSGVO verwendet und welche Rechtsfolgen daraus entstehen.

Massgebliche Primaer-/Aufsichtsquellen:

- [DSGVO, insbesondere Art. 4 Nr. 14, Art. 5, 6, 9, 13, 15, 17, 20, 25, 30, 32 und 35](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679)
- [EDSA-Leitlinien 3/2019 zur Verarbeitung personenbezogener Daten durch Videogeraete](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_de)
- [DSK-Orientierungshilfe Videoueberwachung](https://www.bfdi.bund.de/SharedDocs/Downloads/DE/DSK/Orientierungshilfen/OH_Video%C3%BCberwachung-n-%C3%B6-Stellen.pdf?__blob=publicationFile&v=5)

## Verbleibende Risiken

- Re-ID kann Personen falsch zusammenfuehren oder dieselbe Person mehrfach zaehlen. Der Tageswert ist keine beweissichere Identitaetsfeststellung.
- Verschluesselte Tages-Re-ID-Profile sind absichtlich nur kurzlebig, stellen aber waehrend des aktiven Tages einen zusaetzlichen datenschutzrechtlich relevanten Datensatz dar.
- Die Applikationsverschluesselung schuetzt sensible Textfelder und Tagesprofile, aber nicht automatisch den gesamten Datentraeger. Fuer produktive Systeme ist zusaetzlich Vollvolume-/Datentraegerverschluesselung zu pruefen.
- RAM, Prozessspeicher und Kameratreiber enthalten fuer die Inferenz kurzfristig Rohbilder. Ein kompromittiertes Betriebssystem oder privilegierter Angreifer kann darauf zugreifen.
- Vollbild-Verpixelung reduziert das Risiko, garantiert aber nicht gegen jede Rekonstruktionsmethode. Der sicherste Videomodus bleibt: keine Vorschau, kein Stream.
- Zaehlergebnisse koennen falsch sein. Keine sicherheits-, arbeits- oder personenbezogenen Entscheidungen allein darauf stuetzen.
- Ob eine Datenschutz-Folgenabschaetzung nach Art. 35, ein Verzeichnis nach Art. 30, Arbeitnehmervertretung oder weitere nationale Regeln erforderlich sind, entscheidet der konkrete Einsatz.
- Vorhandene Git-Historie kann alte Artefakte weiterhin enthalten. Sie muss separat bereinigt und alle bereits verteilten Klone/Backups muessen behandelt werden.
- Python- und Android-Abhaengigkeiten sind nicht vollstaendig reproduzierbar gelockt; vor Produktion sind Lockfiles/SBOM, Signatur- bzw. Hashpruefung und ein aktueller Schwachstellenscan in CI erforderlich.
- Die Betreiberfelder in der Konfiguration sind technische Sperren, keine inhaltliche Rechtspruefung. Falsche oder unvollstaendige Angaben koennen vom Code nicht erkannt werden.
