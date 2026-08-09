# Datenschutzprüfung Deutschland – PersonenZähler

Stand: August 2026. Dieses Dokument ist eine technische Datenschutzprüfung und keine individuelle Rechtsberatung. Ob ein konkreter Einsatz zulässig ist, hängt insbesondere von Ort, Verantwortlichem, Zweck, betroffenen Personengruppen, Kamerawinkel und organisatorischem Umfeld ab.

## Kurzfazit

Das System kann datenschutzfreundlich ausgelegt werden, ist aber **nicht allein durch lokale Verarbeitung automatisch DSGVO-konform**. Schon die kurzfristige Aufnahme und KI-Auswertung identifizierbarer Personen ist eine Verarbeitung personenbezogener Daten. Die sichere Produktstrategie lautet daher: möglichst kleiner Aufnahmebereich, keine dauerhafte Bildspeicherung, keine Gesichtserkennung, keine Namenszuordnung, lokale Verarbeitung, kurze Speicherfristen, klare Rechtsgrundlage, transparente Hinweise und technische Sperren gegen unzulässige Konfigurationen.

OSNet-ReID ist rechtlich sensibler als reine anonyme Zählung. Es erzeugt Merkmalsvektoren, mit denen dieselbe Person kameraübergreifend wiedererkannt werden soll. Ob dies im konkreten Einsatz bereits als Verarbeitung biometrischer Daten im Sinne von Art. 4 Nr. 14 und Art. 9 DSGVO einzuordnen ist, hängt insbesondere davon ab, ob die Verarbeitung der eindeutigen Identifizierung dient. Wegen des Zwecks der Wiedererkennung behandeln wir ReID technisch **konservativ als besonders schutzbedürftige personenbezogene Merkmalsverarbeitung**. Embeddings dürfen deshalb nicht persistiert werden und benötigen eine gesonderte Freigabe im Deployment.

## Primärquellen

- DSGVO: insbesondere Art. 5, 6, 13, 25, 30, 32 und 35; bei biometrischer Identifizierung zusätzlich Art. 9. Quelle: EUR-Lex, Verordnung (EU) 2016/679.
- Europäischer Datenschutzausschuss, Leitlinien 3/2019 zur Verarbeitung personenbezogener Daten durch Videogeräte, finale Fassung vom 30.01.2020.
- Datenschutzkonferenz (DSK), Orientierungshilfen zu Videoüberwachung sowie aktuelle Orientierungshilfen zu KI und technischen/organisatorischen Maßnahmen.

## Technische Mindestanforderungen vor Livebetrieb

### Aufnahme und Bilddaten

- Keine permanente Video- oder Einzelbildspeicherung.
- Rohframes existieren nur so lange, wie sie für Decoding und Inferenz erforderlich sind.
- Vorschau standardmäßig aus.
- Falls eine lokale Vorschau bewusst aktiviert wird: Vollbild-Anonymisierung als sicherer Standard.
- Öffentliche Wege, Nachbargrundstücke, Arbeitsplätze oder andere nicht erforderliche Bereiche durch Kameraposition und Masken aus dem Erfassungsbereich entfernen.
- Kein Audio erfassen.
- Keine Gesichtserkennung und keine Zuordnung zu Namen, Mitarbeiter-IDs oder anderen Identitäten.

### ReID

- OSNet-Embeddings nur im RAM.
- Keine Speicherung in SQLite, Logs, Crash-Dumps oder Exporten.
- Automatisches Verwerfen spätestens nach dem technisch erforderlichen Zeitfenster.
- ReID darf ausschließlich zur Vermeidung von Doppelzählungen bzw. zur Passagezuordnung dienen.
- Kein Personenprofil, keine Historie „Person X war wann wo“, kein Langzeittracking.
- Wenn der gleiche Zählzweck am konkreten Standort zuverlässig ohne ReID erreichbar ist, ist die weniger eingriffsintensive Variante vorzuziehen.

### Datenbank und Logs

Standardmäßig werden nur aggregierte Zähler gespeichert. Granulare Ereignisse bleiben aus. Werden Ereignisse für wissenschaftliche Validierung benötigt, gilt:

- separater Forschungsmodus,
- dokumentierter Zweck,
- minimale Felder,
- kurze Aufbewahrung,
- Verschlüsselung,
- keine Rohbilder,
- keine persistenten OSNet-Embeddings,
- keine direkt wiedererkennbaren IDs.

Logs dürfen keine RTSP-Zugangsdaten, Tokens, Bildkoordinaten, Bounding Boxes oder ReID-Vektoren enthalten.

## Rechtsgrundlage und Verhältnismäßigkeit

Der Betreiber muss vor Aktivierung festlegen, auf welche Rechtsgrundlage er sich stützt. Bei privaten Verantwortlichen kommt häufig ein berechtigtes Interesse nach Art. 6 Abs. 1 lit. f DSGVO in Betracht; das ist jedoch keine automatische Freigabe. Erforderlich sind ein konkretes Interesse, Erforderlichkeit und eine Interessenabwägung. Eine Einwilligung ist für frei zugängliche Videoerfassung häufig ungeeignet, weil sie tatsächlich freiwillig und widerrufbar sein müsste.

Die Software kann diese juristische Prüfung nicht selbst durchführen. Sie kann nur verhindern, dass Kameras ohne dokumentierte Betreiberangaben gestartet werden.

## Transparenz

Vor Betreten des Erfassungsbereichs muss die betroffene Person erkennen können, dass eine kamerabasierte Verarbeitung stattfindet. Der Hinweis sollte mindestens Verantwortlichen, Zweck und eine leicht erreichbare Stelle für weitere Datenschutzinformationen nennen. Die ausführlichen Informationen nach Art. 13 DSGVO müssen verfügbar sein.

Für Jugend forscht sollte zusätzlich verständlich erklärt werden:

- Es wird gezählt, nicht identifiziert.
- Bilder werden nicht dauerhaft gespeichert.
- Die KI läuft lokal.
- ReID dient nur der technischen Doppelzählungsvermeidung.
- ReID-Merkmale werden nach kurzer Zeit verworfen.

## Datenschutz-Folgenabschätzung

Eine DSFA nach Art. 35 DSGVO kann erforderlich sein, insbesondere bei systematischer umfangreicher Überwachung öffentlich zugänglicher Bereiche oder bei besonders risikoreicher biometrischer Verarbeitung. Der Code darf deshalb niemals anzeigen „DSGVO-konform“ oder „DSFA nicht erforderlich“. Stattdessen zeigt die Inbetriebnahme einen Status wie `Datenschutzprüfung durch Betreiber erforderlich`.

## Beschäftigte, Schule, öffentliche Bereiche

In Arbeitsumgebungen können zusätzlich Beschäftigtendatenschutz und Beteiligungsrechte relevant sein. In Schulen, öffentlichen Einrichtungen oder öffentlich zugänglichen Bereichen können zusätzliche nationale bzw. landesrechtliche Vorgaben gelten. Diese Einsatzfälle müssen getrennt bewertet werden.

## Generative lokale KI

Der lokale Gemma-Assistent erhält standardmäßig keine Rohframes, keine Personencrops, keine ReID-Embeddings und keine granularen Ereignisdaten. Sein Projekt-RAG schließt `data/`, `logs/` und `models/` aus und redigiert potenzielle Zugangsdaten. Dadurch wird verhindert, dass eine Chat-Frage versehentlich Überwachungsdaten in den Modellkontext zieht.

Externe KI- oder Coding-Dienste sind im Produktionsstandard deaktiviert. Eine spätere optionale externe Eskalation darf nur nach bewusster Aktivierung und mit sichtbarer Vorschau der zu übertragenden Daten erfolgen.

## Technische Privacy Gates

Vor Kamerastart müssen mindestens folgende Prüfungen erfolgreich sein:

1. `privacy.enabled == true`
2. lokale Verarbeitung aktiv
3. externe Telemetrie aus
4. Videoaufzeichnung aus
5. Rechtsgrundlage dokumentiert
6. Zweck dokumentiert
7. Verantwortlicher und Kontakt dokumentiert
8. Datenschutzhinweis bestätigt
9. keine Remote-API ohne Authentifizierung und TLS
10. keine persistenten ReID-Embeddings
11. keine Secrets in Repository oder Logs
12. Kameramasken und Erfassungsbereich vor Ort geprüft

## Offene Punkte für die reale Abnahme

Eine endgültige Bewertung kann erst erfolgen, wenn der konkrete Einsatzort bekannt ist. Dann müssen Kamerawinkel, Sichtbereich, Passantenbezug, organisatorischer Zweck, Hinweisschild, Zugriffsberechtigungen, tatsächliche Aufbewahrung und die Notwendigkeit von ReID geprüft werden.

Bis dahin gilt: **technisch datenschutzfreundlich vorbereitet, aber keine pauschale Konformitätszusage.**
