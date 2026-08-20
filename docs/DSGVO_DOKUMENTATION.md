# DSGVO-Dokumentation für den PersonenZähler

**Stand:** 18. August 2026  
**Projekt:** `1234Taschenlampe/PersonenZ-hler`  
**Geltungsbereich:** lokale kameragestützte Personen-, Belegungs- und Tagesbesucherzählung auf Raspberry Pi 5 / Hailo-10H

> **Hinweis:** Dieses Dokument ist eine technische und organisatorische Vorlage und keine Rechtsberatung. Ein konkreter Einsatz ist nicht allein deshalb DSGVO-konform, weil die hier beschriebenen Schutzmaßnahmen technisch vorhanden sind. Einsatzort, Zweck, Rechtsgrundlage, Betroffenengruppen und tatsächliche Konfiguration müssen vor Livebetrieb geprüft werden.

---

## 1. System und Verarbeitungszwecke

Das System verarbeitet zwei Kamerastreams lokal auf einem Raspberry Pi 5 mit Hailo-10H. YOLO26m erkennt ausschließlich die COCO-Klasse `person`. ByteTrack, Linienlogik und Kamera-Konsens bilden daraus bestätigte Ein- und Austritte.

Die produktiven Zähler haben folgende Bedeutung:

| Zähler | Bedeutung |
| --- | --- |
| Aktuell im Gebäude | +1 bei bestätigtem Eintritt, -1 bei bestätigtem Austritt |
| Besucher heute (eindeutig) | dieselbe durch Re-ID wiedererkannte Person wird pro lokalem Kalendertag nur einmal gezählt |
| Eintritte gesamt | jeder bestätigte Eintritt |
| Austritte gesamt | jeder bestätigte Austritt |
| Durchfluss gesamt | Eintritte gesamt + Austritte gesamt |

Die reine Sichtbarkeit einer Person in einem Kamerabild verändert die Belegung nicht. Dadurch führen kurze Verdeckungen oder Tracking-Verluste nicht unmittelbar zu einem Austritt.

---

## 2. Verantwortlicher Betreiber

Vor Inbetriebnahme auszufüllen:

| Angabe | Wert |
| --- | --- |
| Verantwortlicher | `[Name/Firma/Organisation]` |
| Anschrift | `[Anschrift]` |
| Kontakt | `[E-Mail/Telefon]` |
| Datenschutzbeauftragter, falls vorhanden | `[Name/Kontakt oder nicht zutreffend]` |
| Einsatzort | `[Standort]` |
| Zweck Belegungszählung | `[konkret beschreiben]` |
| Zweck eindeutige Tagesbesucher/Re-ID | `[konkret beschreiben oder deaktiviert]` |
| Rechtsgrundlage Belegungszählung | `[Ergebnis der Prüfung]` |
| Rechtsgrundlage Re-ID | `[gesondertes Ergebnis der Prüfung]` |
| Berechtigtes Interesse, falls einschlägig | `[konkret beschreiben]` |
| Datum der Freigabe | `[Datum]` |

Verantwortlich ist grundsätzlich die Stelle, die über Zweck und Mittel des konkreten Einsatzes entscheidet.

---

## 3. Verarbeitete Daten

### 3.1 Flüchtige Kamerabilder

Kameraframes werden für die lokale Inferenz verarbeitet. Sie werden im vorgesehenen Betrieb nicht dauerhaft als Einzelbild oder Video gespeichert. Kurzzeitig können Frames jedoch im RAM, in Kameratreibern oder temporären Puffern vorhanden sein.

### 3.2 Detektions- und Trackingdaten

Während der Laufzeit entstehen unter anderem Bounding-Boxes, Konfidenzwerte, lokale Track-IDs, technische globale IDs, Zeitpunkte und Bewegungsrichtungen. Bei `database.store_events: false` werden diese nicht als dauerhafte granulare Passagehistorie gespeichert.

### 3.3 Re-ID-Merkmalsvektoren für eindeutige Tagesbesucher

Für den Zähler „Besucher heute (eindeutig)“ erzeugt OSNet normalisierte Merkmalsvektoren aus dem Erscheinungsbild einer Person. Diese dienen ausschließlich dazu, einen späteren Eintritt am selben Kalendertag mit bereits gesehenen Tagesprofilen zu vergleichen.

Es werden dabei keine Namen zugeordnet und keine Gesichtserkennung durchgeführt. Gleichwohl ist diese Wiedererkennung datenschutzrechtlich deutlich eingriffsintensiver als eine reine Personendetektion. Der Betreiber muss deshalb gesondert prüfen, ob die konkrete Verarbeitung Merkmale zur eindeutigen Identifizierung im Sinne der Definition biometrischer Daten nach Art. 4 Nr. 14 DSGVO verwendet und welche Anforderungen sich daraus insbesondere aus Art. 9 DSGVO ergeben.

### 3.4 Aggregierte Zähler

Persistiert werden insbesondere Eintritte, Austritte und aktuelle Belegung. Der Durchfluss wird daraus berechnet. Diese aggregierten Werte sind wesentlich weniger personenbeziehbar als Rohbilder oder Re-ID-Profile, der vorgelagerte Verarbeitungsvorgang bleibt jedoch rechtlich relevant.

---

## 4. Re-ID-Speicherung und Löschung

Ist `VISITOR_COUNTER_DATA_KEY` eingerichtet, speichert das System Re-ID-Tagesprofile verschlüsselt in:

```text
data/daily_unique.sqlite3
```

Dabei gelten folgende technische Regeln:

- ausschließlich Profile des aktiven lokalen Kalendertages,
- Fernet-Verschlüsselung der gespeicherten Merkmalsvektoren,
- Dateirechte `0600`, soweit das Betriebssystem dies unterstützt,
- `secure_delete` in SQLite,
- automatische Löschung von Profilen vergangener Tage beim Tageswechsel,
- keine Speicherung von Namen oder Gesichtsbildern in dieser Datenbank.

Ohne `VISITOR_COUNTER_DATA_KEY` verbleiben Tagesprofile nur im RAM. In diesem Fall kann ein Neustart zu Doppelzählungen beim eindeutigen Tageszähler führen; die GUI markiert diesen Zustand als eingeschränkt.

---

## 5. Datenschutzfreundliche Voreinstellungen

Das Projekt sieht insbesondere folgende Schutzmaßnahmen vor:

- lokale Inferenz auf Raspberry Pi/Hailo,
- keine Cloud-Telemetrie,
- `database.store_video_frames: false`,
- `database.store_events: false` im Standardbetrieb,
- `display.show_camera_preview: false`,
- `privacy.video_stream_enabled: false`,
- API standardmäßig nur auf `127.0.0.1`,
- API-Authentifizierung mit getrennten Rollen/Tokens,
- Secrets außerhalb des Git-Repositories,
- verschlüsselte Tages-Re-ID-Profile,
- tägliche Löschung der Re-ID-Profile,
- keine namentliche Identifizierung.

Die Kameraverarbeitung wird zusätzlich blockiert, solange die erforderlichen Betreiberangaben und die Datenschutz-Freigabe in der Konfiguration fehlen.

---

## 6. Rechtsgrundlage und Erforderlichkeit

Die Rechtsgrundlage muss für den tatsächlichen Einsatz dokumentiert werden. Bei privaten Verantwortlichen kann je nach Einzelfall Art. 6 Abs. 1 lit. f DSGVO in Betracht kommen, sofern ein konkretes berechtigtes Interesse besteht, die Verarbeitung erforderlich ist und die Interessen bzw. Grundrechte betroffener Personen nicht überwiegen.

Die **Tages-Re-ID ist getrennt von der reinen Belegungszählung zu prüfen**. Dass eine Kamera für eine aktuelle Belegungszahl erforderlich oder vertretbar sein kann, bedeutet nicht automatisch, dass eine Wiedererkennung über Stunden hinweg ebenfalls erforderlich ist.

Mindestens zu dokumentieren sind:

1. konkreter Zweck,
2. Prüfung weniger eingriffsintensiver Alternativen,
3. räumliche Begrenzung des Erfassungsbereichs,
4. konkrete Speicherdauer,
5. Interessenabwägung, soweit einschlägig,
6. gesonderte Bewertung der Re-ID,
7. Transparenz vor Betreten des Erfassungsbereichs,
8. Prüfung einer Datenschutz-Folgenabschätzung.

Für Beschäftigte, Kinder, öffentliche Räume oder andere besonders sensible Konstellationen können zusätzliche Anforderungen gelten.

---

## 7. Transparenz nach Art. 13 DSGVO

Vor dem Erfassungsbereich ist ein gut sichtbarer Hinweis anzubringen. Das Projekt enthält dafür [`PRIVACY_NOTICE_TEMPLATE.md`](PRIVACY_NOTICE_TEMPLATE.md).

Wenn der eindeutige Tagesbesucherzähler aktiv ist, muss die Information ausdrücklich auf die lokale Wiedererkennung/Re-ID und die tägliche Löschung der Profile hinweisen. Die Funktion darf nicht als vollständig „anonyme Besucherzählung“ beschrieben werden.

Die vollständige Information sollte mindestens enthalten:

- Verantwortlichen und Kontaktdaten,
- Zweck(e), einschließlich Re-ID-Zweck,
- Rechtsgrundlage(n),
- berechtigte Interessen, soweit einschlägig,
- Empfänger,
- Speicherdauer,
- Betroffenenrechte,
- Beschwerderecht,
- Hinweis auf etwaige Re-ID-/automatisierte Vergleichslogik,
- Drittlandtransfers, falls solche entgegen dem lokalen Standard eingerichtet werden.

---

## 8. Technische und organisatorische Maßnahmen nach Art. 32 DSGVO

Vorgesehen sind insbesondere:

- lokale Verarbeitung ohne externe Telemetrie,
- Zugriffsschutz über Linux-Dateirechte,
- externe Schlüsselablage,
- Fernet-Verschlüsselung sensibler Felder und Tagesprofile,
- HMAC-basierte Pseudonymisierung bei optionaler Ereignisspeicherung,
- kurze Löschfristen,
- API-Authentifizierung und Rollen,
- TLS-Pflicht bei nicht-lokaler API-Bindung,
- keine CORS-Wildcard,
- Logfilter ohne Bilder und ohne rohe Personen-/Track-IDs,
- restriktive systemd-Optionen,
- keine produktiven Secrets im Repository.

Für einen realen Produktiveinsatz sollte zusätzlich eine Datenträger- bzw. Vollvolume-Verschlüsselung geprüft werden.

---

## 9. Datenschutz-Folgenabschätzung

Ob eine DSFA nach Art. 35 DSGVO erforderlich ist, hängt vom konkreten Einsatz ab. Eine vertiefte Prüfung ist insbesondere angezeigt, wenn systematisch öffentlich zugängliche Bereiche beobachtet werden, viele Personen betroffen sind, Beschäftigte erfasst werden oder Re-ID zur Wiedererkennung eingesetzt wird.

Eine DSFA sollte mindestens betrachten:

- Notwendigkeit und Verhältnismäßigkeit,
- Risiken falscher Re-ID-Zuordnungen,
- Risiken unbefugten Zugriffs auf Tagesprofile,
- Missbrauch zu Verhaltens- oder Leistungskontrolle,
- Erfassungsbereich und Ausweichmöglichkeiten,
- Löschmechanismen und Schlüsselschutz,
- organisatorische Zugriffsbeschränkungen.

---

## 10. Verzeichnis von Verarbeitungstätigkeiten – Kurzvorlage

| Feld | Eintrag |
| --- | --- |
| Verarbeitung | Lokale kamerabasierte Belegungs- und Besucherzählung |
| Verantwortlicher | `[eintragen]` |
| Zwecke | `[Belegung / Durchfluss / eindeutige Tagesbesucher]` |
| Betroffene | `[Besucher/Kunden/Beschäftigte/etc.]` |
| Datenarten | flüchtige Bilddaten, Trackingdaten, ggf. Tages-Re-ID-Profile, aggregierte Zähler |
| Empfänger | `[eintragen]` |
| Drittlandtransfer | im lokalen Standard keiner |
| Löschung | keine dauerhaften Bilder; Re-ID-Profile beim Tageswechsel; weitere Fristen dokumentieren |
| TOMs | lokale Verarbeitung, Verschlüsselung, Zugriffsschutz, Authentifizierung, Löschung |

---

## 11. Betroffenenrechte

Je nach Voraussetzungen bestehen insbesondere Rechte nach Art. 15 bis 21 DSGVO. Da keine Namenszuordnung vorgesehen ist, kann eine konkrete Zuordnung technischer Re-ID-Profile zu einer namentlich benannten Person praktisch eingeschränkt oder unmöglich sein. Das beseitigt die datenschutzrechtlichen Pflichten nicht.

Anfragen sind an den dokumentierten Verantwortlichen zu richten.

---

## 12. Datenschutzverletzungen

Bei Verdacht auf unbefugten Zugriff, Verlust eines Geräts, Schlüsselkompromittierung oder ungewollte Datenübertragung sind mindestens zu prüfen:

1. betroffene Daten und Zeitraum,
2. betroffene Personengruppen,
3. Zugriff auf Re-ID-/Ereignisdaten,
4. Kompromittierung von Schlüsseln oder Tokens,
5. Eindämmung und Schlüsselrotation,
6. Dokumentations- und gegebenenfalls Meldepflichten nach Art. 33/34 DSGVO.

---

## 13. Inbetriebnahme-Checkliste

- [ ] Verantwortlichen und Kontakt eingetragen
- [ ] konkreten Zweck der Belegungszählung dokumentiert
- [ ] Re-ID-Zweck separat dokumentiert oder Re-ID deaktiviert
- [ ] Rechtsgrundlage(n) geprüft
- [ ] Interessenabwägung erstellt, soweit erforderlich
- [ ] DSFA-Prüfung dokumentiert
- [ ] Kamerawinkel auf notwendigen Bereich begrenzt
- [ ] Datenschutzhinweis vor dem Bereich angebracht
- [ ] `VISITOR_COUNTER_DATA_KEY` außerhalb des Repositories erzeugt
- [ ] Löschung der Re-ID-Profile beim Tageswechsel getestet
- [ ] Neustarttest des Tageszählers durchgeführt
- [ ] API/Remotezugriff auf erforderliches Minimum begrenzt
- [ ] keine Bilder/Videos unerwartet persistent gespeichert
- [ ] Zugriffsrechte und Logs geprüft

---

## 14. Maßgebliche Quellen

- [DSGVO – Verordnung (EU) 2016/679](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679)
- [EDSA-Leitlinien 3/2019 zur Verarbeitung personenbezogener Daten durch Videogeräte](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_de)
- [DSK-Orientierungshilfe Videoüberwachung](https://www.bfdi.bund.de/SharedDocs/Downloads/DE/DSK/Orientierungshilfen/OH_Video%C3%BCberwachung-n-%C3%B6-Stellen.pdf?__blob=publicationFile&v=5)

---

## 15. Verbleibende technische Risiken

- Re-ID ist probabilistisch: dieselbe Person kann doppelt gezählt, unterschiedliche Personen können zusammengeführt werden.
- Ein kompromittiertes Betriebssystem kann auf Frames oder entschlüsselte Merkmalsvektoren im RAM zugreifen.
- Verschlüsselung schützt nicht gegen Missbrauch durch einen bereits berechtigten Prozess.
- Die aktuelle Belegung kann nach Stromausfall oder Betriebspause von der realen Belegung abweichen, wenn während der Ausfallzeit Personen den Bereich betreten oder verlassen.
- Eine falsch gewählte Re-ID-Schwelle beeinflusst die statistische Genauigkeit des Tageszählers.

Die Ergebnisse sind daher als statistische Zählwerte und nicht als beweissichere Identitäts- oder Anwesenheitsfeststellung zu behandeln.
