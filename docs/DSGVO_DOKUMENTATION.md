# DSGVO-Dokumentation für den PersonenZähler

**Stand:** 18. August 2026  
**Projekt:** `1234Taschenlampe/PersonenZ-hler`  
**Geltungsbereich:** Raspberry-Pi-/Hailo-basierte, lokale kameragestützte Personenzählung

> **Wichtiger Hinweis:** Dieses Dokument ist eine technische und organisatorische Vorlage für den Betreiber und keine Rechtsberatung. Ob ein konkreter Einsatz zulässig und DSGVO-konform ist, hängt insbesondere vom Einsatzort, dem Erfassungsbereich, dem Zweck, der Rechtsgrundlage, den betroffenen Personengruppen und der tatsächlichen Konfiguration ab. Vor einem produktiven Einsatz müssen die als Platzhalter gekennzeichneten Angaben ausgefüllt und die Rechtsgrundlage sowie gegebenenfalls eine Datenschutz-Folgenabschätzung geprüft werden.

---

## 1. Zweck dieses Dokuments

Dieses Dokument beschreibt die datenschutzrechtlich relevanten Eigenschaften des PersonenZähler-Systems, die vorgesehenen datenschutzfreundlichen Voreinstellungen, die Verarbeitungsvorgänge sowie die vom jeweiligen Betreiber zu erfüllenden organisatorischen Pflichten.

Es dient insbesondere als Grundlage für:

- die Dokumentation nach den Grundsätzen der Rechenschaftspflicht gemäß Art. 5 Abs. 2 DSGVO,
- die Prüfung von Datenschutz durch Technikgestaltung und datenschutzfreundliche Voreinstellungen gemäß Art. 25 DSGVO,
- die Dokumentation technischer und organisatorischer Maßnahmen gemäß Art. 32 DSGVO,
- die Vorbereitung eines Verzeichnisses von Verarbeitungstätigkeiten gemäß Art. 30 DSGVO,
- die Transparenzinformationen gemäß Art. 13 DSGVO,
- die Prüfung, ob eine Datenschutz-Folgenabschätzung gemäß Art. 35 DSGVO erforderlich ist.

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
| Konkreter Zweck | `[konkreten betrieblichen Zweck eintragen]` |
| Rechtsgrundlage | `[Ergebnis der rechtlichen Prüfung]` |
| Berechtigtes Interesse, falls Art. 6 Abs. 1 lit. f DSGVO | `[konkret beschreiben]` |
| Datum der Freigabe | `[Datum]` |
| Zuständige Stelle für Betroffenenanfragen | `[Kontakt]` |

Derjenige, der über Zweck und Mittel des konkreten Einsatzes entscheidet, ist grundsätzlich als Verantwortlicher im Sinne der DSGVO zu betrachten. Der Quellcode oder der Entwickler des Projekts ersetzt diese Betreiberverantwortung nicht.

---

## 3. Systembeschreibung

Das System ist als lokale Edge-AI-Anwendung zur kamerabasierten Zählung von Personen ausgelegt. Die produktive Erkennung erfolgt mit einem YOLO26m-COCO-Detection-Modell auf einem Hailo-10H-Beschleuniger. Aus den Kamerabildern werden Personendetektionen abgeleitet, die anschließend durch Tracking- und Zähllogik verarbeitet werden.

Die aktuelle Standardkonfiguration sieht unter anderem vor:

- lokale Verarbeitung auf Raspberry Pi/Hailo,
- keine Cloud-Telemetrie,
- keine dauerhafte Speicherung von Videoframes,
- keine Speicherung granularer Personenereignisse im Standardbetrieb,
- keine standardmäßig sichtbare Kameravorschau,
- deaktiviertes Remote-Video,
- deaktivierte Re-Identification im sicheren Standard,
- API-Bindung an `127.0.0.1`,
- rollenbasierte API-Tokens,
- Verschlüsselungspflicht, sobald granulare Ereignisspeicherung aktiviert wird.

Das System ist damit auf Datenminimierung ausgelegt. Gleichwohl werden während der laufenden Inferenz kurzfristig Bilddaten im Arbeitsspeicher bzw. in Kamerapuffern verarbeitet. Die Tatsache, dass keine Bilder dauerhaft gespeichert werden, bedeutet daher nicht, dass überhaupt keine Verarbeitung personenbezogener Daten stattfindet.

---

## 4. Kategorien betroffener Personen

Je nach Einsatzort können insbesondere folgende Personengruppen betroffen sein:

- Besucher,
- Kunden,
- Beschäftigte,
- Dienstleister,
- Lieferanten,
- sonstige Personen, die den Erfassungsbereich durchqueren.

Besonders schutzbedürftige Gruppen, etwa Kinder, Beschäftigte oder Personen in sensiblen Bereichen, müssen bei der Interessenabwägung und bei der Prüfung einer Datenschutz-Folgenabschätzung besonders berücksichtigt werden.

---

## 5. Kategorien verarbeiteter Daten

### 5.1 Flüchtig verarbeitete Bilddaten

Während der Erkennung werden Kameraframes technisch verarbeitet. Sie können Merkmale natürlicher Personen enthalten, beispielsweise Körperform, Kleidung, Bewegungsrichtung sowie abhängig vom Bildausschnitt auch Gesichter oder Kennzeichen.

Das produktive System ist nicht auf Gesichtserkennung ausgelegt. Es werden keine Namen oder Identitäten aus Gesichtern abgeleitet. Eine bloße Personendetektion ist jedoch weiterhin eine Verarbeitung von Bildinformationen und kann datenschutzrechtlich relevant sein.

### 5.2 Detektions- und Trackingdaten

Während der Verarbeitung können unter anderem entstehen:

- lokale Track-IDs,
- globale technische Personen-IDs,
- Zeitpunkte,
- Kamera-ID,
- Bewegungs-/Passagerichtung,
- Detektionskonfidenz,
- Statusinformationen zum Eintritt/Austritt,
- technische Diagnoseinformationen.

Im Standardbetrieb mit deaktivierter Ereignisspeicherung werden diese Informationen nicht als dauerhafte granulare Personenhistorie gespeichert.

### 5.3 Aggregierte Zähler

Gespeichert werden insbesondere aggregierte Werte wie:

- Anzahl Eintritte,
- Anzahl Austritte,
- aktuell berechnete Belegung.

Rein aggregierte Zähler ohne Personenbezug sind grundsätzlich datenschutzrechtlich weniger kritisch. Entscheidend ist jedoch der gesamte vorgelagerte Verarbeitungsvorgang.

### 5.4 Optionale Ereignisdaten

Wenn `database.store_events` bewusst aktiviert wird, können zusätzliche Ereignisdaten gespeichert werden. Das System verlangt dafür einen externen Verschlüsselungsschlüssel. Personen- und Track-IDs werden schlüsselgebunden pseudonymisiert; sensible Textfelder werden verschlüsselt.

Pseudonymisierte Daten sind nicht automatisch anonym. Sie können weiterhin personenbezogene Daten im Sinne der DSGVO darstellen.

---

## 6. Zwecke der Verarbeitung

Der Zweck muss vor Inbetriebnahme konkret und nachvollziehbar festgelegt werden. Eine Formulierung wie „Sicherheit“ oder „Analyse“ allein ist regelmäßig zu unbestimmt.

Zulässige Zwecke müssen für den konkreten Einsatz geprüft werden. Ein möglicher technischer Zweck des Systems ist beispielsweise:

> Ermittlung der aktuellen Auslastung und aggregierter Ein-/Austrittszahlen eines räumlich begrenzten Bereichs ohne dauerhafte Speicherung von Bildmaterial und ohne Identifizierung einzelner Personen.

Eine Zweckänderung, beispielsweise von reiner Auslastungszählung hin zu Verhaltens-, Leistungs- oder Beschäftigtenkontrolle, darf nicht stillschweigend erfolgen und erfordert eine erneute rechtliche Bewertung.

---

## 7. Rechtsgrundlage

Die Rechtsgrundlage muss der Betreiber für den konkreten Einsatz festlegen und dokumentieren.

Bei einem privaten Betreiber kann je nach Einzelfall insbesondere Art. 6 Abs. 1 lit. f DSGVO in Betracht kommen, wenn ein konkretes berechtigtes Interesse besteht, die Verarbeitung erforderlich ist und die Interessen, Grundrechte und Grundfreiheiten der betroffenen Personen nicht überwiegen. Diese Abwägung ist vor Inbetriebnahme schriftlich zu dokumentieren.

Bei öffentlich zugänglichen Räumen sind zusätzlich die jeweils einschlägigen nationalen Vorschriften zu prüfen. In Deutschland ist insbesondere § 4 BDSG für Videoüberwachung öffentlich zugänglicher Räume zu berücksichtigen. Daraus darf nicht abgeleitet werden, dass jeder Personenzähler automatisch unter denselben Voraussetzungen zulässig ist; der konkrete technische und tatsächliche Einsatz ist maßgeblich.

Eine Einwilligung sollte nicht nur deshalb gewählt werden, weil sie scheinbar einfach dokumentierbar ist. Sie ist nur geeignet, wenn sie tatsächlich freiwillig, informiert, spezifisch und widerrufbar erteilt werden kann und keine Nachteile bei Verweigerung entstehen.

Für Beschäftigte können zusätzliche arbeits- und datenschutzrechtliche Anforderungen gelten. Ein Einsatz zur individuellen Leistungs- oder Verhaltenskontrolle ist mit dem vorgesehenen Zweck dieses Projekts nicht vereinbar und erfordert eine gesonderte rechtliche Prüfung.

---

## 8. Interessenabwägung bei Art. 6 Abs. 1 lit. f DSGVO

Falls sich der Betreiber auf berechtigte Interessen stützt, ist mindestens zu dokumentieren:

1. **Berechtigtes Interesse:** Welches konkrete und gegenwärtige Interesse wird verfolgt?
2. **Erforderlichkeit:** Warum ist die kamerabasierte Zählung zur Zweckerreichung notwendig? Welche weniger eingriffsintensiven Alternativen wurden geprüft?
3. **Abwägung:** Welche Auswirkungen entstehen für betroffene Personen und warum überwiegen diese nicht?
4. **Schutzmaßnahmen:** Welche technischen und organisatorischen Maßnahmen reduzieren das Risiko?
5. **Erfassungsbereich:** Warum ist der Kamerabereich räumlich auf das notwendige Minimum begrenzt?
6. **Speicherung:** Warum ist keine bzw. nur eine sehr kurze personenbezogene Speicherung erforderlich?
7. **Transparenz:** Wie werden Personen vor Betreten des Erfassungsbereichs informiert?

Die Abwägung ist erneut durchzuführen, wenn sich Zweck, Kameraposition, Modell, Speicherverhalten, Remotezugriff oder Nutzerkreis wesentlich ändern.

---

## 9. Datenschutz durch Technikgestaltung und datenschutzfreundliche Voreinstellungen

Die aktuelle Projektkonfiguration setzt mehrere datenschutzfreundliche Standardeinstellungen um:

### 9.1 Lokale Verarbeitung

`privacy.local_processing_only: true` und `privacy.telemetry_enabled: false` sind als sichere Voreinstellungen vorgesehen. Im produktiven Laufzeitcode ist keine Cloud-Analytics- oder Telemetrieintegration vorgesehen.

### 9.2 Keine dauerhafte Bildspeicherung

`database.store_video_frames: false` verhindert die vorgesehene dauerhafte Speicherung von Videoframes. Kurzlebige technische Frames können für die Inferenz dennoch vorübergehend im RAM, in Treiberpuffern oder in temporären Speicherbereichen vorhanden sein.

### 9.3 Keine granulare Ereignisspeicherung im Standardbetrieb

`database.store_events: false` ist der datenschutzfreundliche Standard. Damit soll die Persistenz personenähnlicher Tracking- und Passageinformationen vermieden werden.

### 9.4 Vorschau und Remote-Video deaktiviert

`display.show_camera_preview: false` und `privacy.video_stream_enabled: false` reduzieren das Risiko zusätzlicher visueller Überwachung. Wird eine Vorschau oder ein Stream aktiviert, muss die Erforderlichkeit separat geprüft werden. Der vorgesehene Anonymisierungsmodus ist `full_frame`.

### 9.5 Re-Identification

Das OSNet-Re-ID-Modell ist nicht als zwingende Funktion vorgesehen (`reid_required: false`). Eine Aktivierung erhöht die datenschutzrechtliche Eingriffsintensität und muss vor Einsatz gesondert bewertet werden. Re-ID-Merkmalsvektoren sollten nicht dauerhaft gespeichert werden.

### 9.6 API-Sicherheit

Der sichere Standard ist:

- Bindung an `127.0.0.1`,
- Authentifizierung aktiviert,
- getrennte Rollen-/Tokens für Viewer, Operator und Admin,
- keine CORS-Wildcard,
- TLS-Anforderung bei nicht-lokaler Bereitstellung.

Remotezugriff sollte nur eingerichtet werden, wenn er für den dokumentierten Zweck erforderlich ist.

---

## 10. Speicherung und Löschkonzept

### Standardbetrieb

| Datenart | Speicherung | vorgesehene Dauer |
| --- | --- | --- |
| Kameraframes | keine dauerhafte Speicherung | nur technisch flüchtig |
| Tracking-/Personenereignisse | standardmäßig aus | keine persistente Historie |
| Aggregierte Zähler | lokal in SQLite | nach Betreiberzweck festzulegen |
| Logs | lokal, ohne Bilder | kurze Rotation gemäß Konfiguration |
| Audit-Log | lokal | Standard: 30 Tage |

### Bei aktivierter Ereignisspeicherung

Die Standardaufbewahrung beträgt 24 Stunden und soll technisch auf höchstens sieben Tage begrenzt bleiben. Abgelaufene Datensätze werden regelmäßig gelöscht. SQLite `secure_delete` ist aktiviert; zusätzlich wird WAL-Truncation eingesetzt.

Der Betreiber muss die tatsächlich erforderliche Löschfrist begründen. Eine technisch mögliche Höchstfrist ist keine rechtliche Rechtfertigung für deren vollständige Ausschöpfung.

Backups, Exportdateien und migrierte Datenbanken sind in das Löschkonzept einzubeziehen. Alte Git-Historien oder bereits verteilte Kopien müssen separat bewertet werden, falls dort früher personenbezogene Artefakte enthalten waren.

---

## 11. Verschlüsselung und Pseudonymisierung

Bei aktivierter granularer Ereignisspeicherung verlangt die Anwendung einen externen Fernet-kompatiblen 32-Byte-Schlüssel.

Vorgesehen sind:

- Fernet-Verschlüsselung sensibler Textfelder,
- HMAC-basierte Pseudonymisierung technischer Personen-/Track-IDs,
- externe Ablage des Schlüssels,
- Dateirechte `0600` für Schlüsseldateien,
- keine Speicherung produktiver Schlüssel im Git-Repository.

Die Anwendung verschlüsselt nicht die gesamte SQLite-Datei. Metadaten wie Zeitpunkte, Richtungen, numerische Konfidenzwerte oder Datenbankstrukturen können daher außerhalb der verschlüsselten Felder sichtbar bleiben. Bei aktivierter Ereignisspeicherung wird für produktive Systeme zusätzlich eine Datenträger-/Volume-Verschlüsselung empfohlen.

---

## 12. Empfänger und Drittlandübermittlung

Im sicheren lokalen Standard sind keine externen Empfänger oder Drittlandübermittlungen vorgesehen.

Wenn der Betreiber jedoch beispielsweise:

- Cloud-Backups,
- externe Monitoringdienste,
- Remote-Support,
- externe Analytics,
- öffentliche API-Endpunkte,
- Synchronisation mit Drittanbietern

hinzufügt, muss die Empfänger- und Drittlandprüfung aktualisiert werden. Gegebenenfalls sind Auftragsverarbeitungsverträge nach Art. 28 DSGVO und die Anforderungen der Art. 44 ff. DSGVO zu beachten.

---

## 13. Transparenz und Informationspflichten

Betroffene Personen müssen grundsätzlich rechtzeitig und verständlich über die Verarbeitung informiert werden. Bei einem Kamerabereich sollte der Hinweis so angebracht sein, dass die Information vor dem Betreten des Erfassungsbereichs wahrgenommen werden kann.

Das Repository enthält dafür `docs/PRIVACY_NOTICE_TEMPLATE.md`.

Mindestens zu nennen bzw. über eine zweite Informationsebene zugänglich zu machen sind:

- Identität und Kontaktdaten des Verantwortlichen,
- gegebenenfalls Datenschutzbeauftragter,
- Zweck,
- Rechtsgrundlage,
- berechtigtes Interesse bei Art. 6 Abs. 1 lit. f DSGVO,
- Kategorien von Empfängern,
- gegebenenfalls Drittlandübermittlungen,
- Speicherdauer bzw. Kriterien dafür,
- Betroffenenrechte,
- Beschwerderecht bei einer Aufsichtsbehörde,
- gegebenenfalls Informationen zu automatisierten Entscheidungen.

---

## 14. Betroffenenrechte

Je nach Verarbeitung und Rechtsgrundlage können insbesondere folgende Rechte bestehen:

- Auskunft nach Art. 15 DSGVO,
- Berichtigung nach Art. 16 DSGVO,
- Löschung nach Art. 17 DSGVO,
- Einschränkung der Verarbeitung nach Art. 18 DSGVO,
- Datenübertragbarkeit nach Art. 20 DSGVO, soweit anwendbar,
- Widerspruch nach Art. 21 DSGVO,
- Beschwerde bei einer zuständigen Datenschutzaufsichtsbehörde nach Art. 77 DSGVO.

Da das System im datenschutzfreundlichen Betrieb bewusst keine dauerhafte Identitätszuordnung führt, kann eine konkrete Person unter Umständen technisch nicht aus aggregierten oder pseudonymisierten Daten herausgefiltert werden. Der Betreiber muss hierfür einen dokumentierten Prozess für Betroffenenanfragen vorhalten und darf nicht nachträglich zusätzliche Identifikationsmerkmale nur zum Zweck der Zuordenbarkeit erheben, wenn dies nicht erforderlich ist.

---

## 15. Keine automatisierten Einzelentscheidungen

Das System ist für Zähl- und Auslastungszwecke vorgesehen. Es soll keine rechtlichen oder ähnlich erheblichen Entscheidungen über einzelne Personen treffen.

Zählergebnisse können technisch fehlerhaft sein. Sie dürfen nicht allein als Grundlage für sicherheitskritische, arbeitsrechtliche, disziplinarische oder personenbezogene Entscheidungen verwendet werden.

---

## 16. Technische und organisatorische Maßnahmen (TOM)

### Zugriffskontrolle

- getrennte API-Rollen,
- starke Tokens mit Mindestlänge,
- produktive Secrets außerhalb des Repositories,
- restriktive Dateirechte,
- keine unbekannten SSH-Hostkeys,
- Remotezugriff nur bei dokumentiertem Bedarf.

### Zugriff auf Daten

- standardmäßig keine Bildvorschau,
- standardmäßig kein Remote-Video,
- keine Cloud-Telemetrie,
- keine dauerhafte Bildspeicherung,
- granulare Ereignisspeicherung standardmäßig deaktiviert.

### Verschlüsselung

- Verschlüsselung sensibler Ereignisfelder,
- Pseudonymisierung technischer IDs,
- TLS für nicht-lokale API-Kommunikation,
- zusätzliche Datenträgerverschlüsselung bei personenbezogener Ereignisspeicherung empfohlen.

### Protokollierung

- Logs ohne Bilder,
- Filterung sensibler IDs/Koordinaten/Secrets,
- Auditierung administrativer Export-/Löschaktionen,
- begrenzte Log-Aufbewahrung.

### Verfügbarkeit und Wiederherstellung

- dokumentierte Deployment-/Recovery-Verfahren,
- regelmäßige Funktions- und Sicherheitsprüfung,
- Backups nur soweit erforderlich und unter Einbeziehung des Löschkonzepts.

### Datenschutzkontrolle

- Pflichtfelder für Zweck, Rechtsgrundlage und Verantwortlichen,
- Inbetriebnahmesperre bis zur Betreiberbestätigung,
- regelmäßige Überprüfung der Konfiguration,
- erneute Datenschutzprüfung bei wesentlichen Änderungen.

---

## 17. Datenschutz-Folgenabschätzung nach Art. 35 DSGVO

Vor Produktiveinsatz ist zu prüfen, ob eine Datenschutz-Folgenabschätzung (DSFA) erforderlich ist.

Eine vertiefte Prüfung ist insbesondere angezeigt bei:

- systematischer umfangreicher Überwachung öffentlich zugänglicher Bereiche,
- besonderer Eingriffsintensität,
- Einsatz in Bereichen mit schutzbedürftigen Personen,
- dauerhafter oder umfangreicher Personenverfolgung,
- Aktivierung von Re-ID oder vergleichbaren Wiedererkennungsfunktionen,
- Verknüpfung mit weiteren Datenquellen,
- Beschäftigtenüberwachung,
- großflächigem oder standortübergreifendem Einsatz.

Wenn voraussichtlich ein hohes Risiko für Rechte und Freiheiten natürlicher Personen besteht, ist eine DSFA vor Beginn der Verarbeitung durchzuführen. Ein technisches System kann diese rechtliche Risikobewertung nicht automatisiert ersetzen.

---

## 18. Verzeichnis von Verarbeitungstätigkeiten – Vorlage

Für ein VVT kann der Betreiber mindestens folgende Angaben übernehmen und konkretisieren:

| Feld | Beschreibung |
| --- | --- |
| Verarbeitungstätigkeit | Lokale kamerabasierte Personenzählung |
| Verantwortlicher | `[eintragen]` |
| Zweck | `[konkret eintragen]` |
| Betroffene Personen | Besucher/Kunden/Beschäftigte/etc. je Einsatz |
| Datenkategorien | flüchtige Kameraframes, Detektions-/Trackingdaten, Zähler, ggf. Ereignisdaten |
| Empfänger | im lokalen Standard keine externen Empfänger |
| Drittlandtransfer | im lokalen Standard keiner |
| Löschfristen | Frames flüchtig; Ereignisse standardmäßig aus; bei Aktivierung kurze definierte Frist; Audit-Logs nach Konfiguration |
| TOM | siehe Abschnitt 16 |
| Rechtsgrundlage | `[eintragen]` |

---

## 19. Datenschutzverletzungen

Der Betreiber benötigt einen Prozess für Sicherheits- und Datenschutzvorfälle.

Bei Verdacht auf eine Verletzung personenbezogener Daten sind mindestens zu prüfen:

1. Welche Daten waren betroffen?
2. Welche Personen bzw. Personengruppen können betroffen sein?
3. Wurden Daten unbefugt offengelegt, verändert, gelöscht oder unzugänglich?
4. Wie hoch ist das Risiko für Rechte und Freiheiten der Betroffenen?
5. Ist eine Meldung an die Aufsichtsbehörde gemäß Art. 33 DSGVO erforderlich?
6. Ist eine Benachrichtigung betroffener Personen gemäß Art. 34 DSGVO erforderlich?
7. Welche Sofortmaßnahmen wurden durchgeführt?
8. Welche dauerhaften Korrekturmaßnahmen werden umgesetzt?

Alle Datenschutzverletzungen und die getroffenen Bewertungen sind nachvollziehbar zu dokumentieren.

---

## 20. Verpflichtende Inbetriebnahmeprüfung

Vor realem Einsatz ist mindestens Folgendes zu erledigen:

- [ ] Verantwortlichen und Kontakt festlegen.
- [ ] Zweck konkret dokumentieren.
- [ ] Rechtsgrundlage dokumentieren.
- [ ] Bei Art. 6 Abs. 1 lit. f DSGVO: Interessenabwägung dokumentieren.
- [ ] Erforderlichkeit und mildere Mittel prüfen.
- [ ] Kamerawinkel auf den notwendigen Bereich begrenzen.
- [ ] Öffentliche Wege, Nachbargrundstücke und irrelevante Bereiche soweit möglich ausblenden/maskieren.
- [ ] Datenschutz-Hinweis vor dem Erfassungsbereich anbringen.
- [ ] Vollständige Art.-13-Information bereitstellen.
- [ ] `privacy_notice_acknowledged` erst nach tatsächlicher Umsetzung aktivieren.
- [ ] Keine produktiven Secrets in Git speichern.
- [ ] Ereignisspeicherung nur bei dokumentierter Notwendigkeit aktivieren.
- [ ] Falls Ereignisspeicherung aktiv: externen Schlüssel und Datenträgerverschlüsselung einrichten.
- [ ] Remote-Video deaktiviert lassen, sofern nicht zwingend erforderlich.
- [ ] Re-ID deaktiviert lassen, sofern nicht separat geprüft und freigegeben.
- [ ] API bei Remotezugriff nur mit TLS und Authentifizierung betreiben.
- [ ] Löschfristen testen.
- [ ] Export- und Löschfunktionen testen.
- [ ] Backup- und Recovery-Prozess auf Datenschutzkonformität prüfen.
- [ ] DSFA-Erforderlichkeit prüfen und Ergebnis dokumentieren.
- [ ] VVT aktualisieren.
- [ ] Regelmäßigen Review-Termin festlegen.

---

## 21. Aktuelle technische Datenschutzparameter im Repository

Die sichere Standardkonfiguration umfasst zum Stand dieses Dokuments insbesondere:

```yaml
database:
  store_video_frames: false
  store_events: false
  retention_hours: 24
  encryption_required: true

display:
  show_camera_preview: false
  anonymization_mode: full_frame

privacy:
  enabled: true
  local_processing_only: true
  telemetry_enabled: false
  video_stream_enabled: false
  privacy_notice_acknowledged: false

api:
  bind_host: 127.0.0.1
  require_auth: true
  audit_retention_days: 30
```

Diese Werte sind technische Voreinstellungen und dürfen nicht mit einer rechtlichen Freigabe gleichgesetzt werden.

---

## 22. Grenzen der Datenschutzmaßnahmen

Folgende Punkte bleiben auch bei sicherer Konfiguration relevant:

- Rohbilder werden während der Inferenz kurzfristig technisch verarbeitet.
- Ein kompromittiertes Betriebssystem oder privilegierter Angreifer kann auf RAM, Treiberpuffer oder Prozessdaten zugreifen.
- Pseudonymisierung ist keine Anonymisierung.
- Feldverschlüsselung ersetzt keine vollständige Datenträgerverschlüsselung.
- Pixelierung oder Anonymisierung reduziert Risiken, garantiert aber keine irreversible Anonymität.
- Technische Zähler können falsch-positive oder falsch-negative Ergebnisse erzeugen.
- Änderungen an Modellen, Kamerapositionen, Netzwerkanbindung oder Speicherlogik können die Datenschutzbewertung wesentlich verändern.
- Das Repository kann Betreiberpflichten nicht automatisch rechtlich bewerten.

---

## 23. Maßgebliche Quellen

- Verordnung (EU) 2016/679 (DSGVO), insbesondere Art. 5, 6, 12–13, 15–21, 25, 28, 30, 32–35 und 44 ff.:  
  https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679
- Europäischer Datenschutzausschuss (EDSA), Leitlinien 3/2019 zur Verarbeitung personenbezogener Daten durch Videogeräte:  
  https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_de
- Deutschland: § 4 BDSG – Videoüberwachung öffentlich zugänglicher Räume:  
  https://www.gesetze-im-internet.de/bdsg_2018/__4.html
- Ergänzendes technisches Datenschutz- und Sicherheitskonzept dieses Projekts:  
  `docs/PRIVACY_AND_SECURITY.md`
- Muster für die Information am Kamerabereich:  
  `docs/PRIVACY_NOTICE_TEMPLATE.md`

---

## 24. Änderungsmanagement

Diese Dokumentation ist zu überprüfen, sobald mindestens einer der folgenden Punkte geändert wird:

- Einsatzzweck,
- Betreiber,
- Standort oder Kamerawinkel,
- Rechtsgrundlage,
- Speicherdauer,
- Aktivierung von Ereignisspeicherung,
- Aktivierung von Re-ID,
- Aktivierung von Bildvorschau oder Videostream,
- Remotezugriff,
- Empfänger oder Cloud-Dienste,
- eingesetztes KI-Modell,
- wesentliche Sicherheitsarchitektur.

Der Betreiber sollte zusätzlich einen regelmäßigen Review durchführen und dokumentieren.

---

**Dokumentstatus:** technische DSGVO-/Betreiberdokumentation mit offenen Betreiberfeldern. Vor produktivem Einsatz sind die offenen Angaben auszufüllen und die konkrete Verarbeitung rechtlich zu prüfen.
