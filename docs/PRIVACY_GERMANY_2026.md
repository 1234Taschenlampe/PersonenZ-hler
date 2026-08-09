# Datenschutzprüfung Deutschland – PersonenZähler

Stand: August 2026. Dieses Dokument ist eine technische Datenschutzprüfung und keine individuelle Rechtsberatung. Die Zulässigkeit eines realen Einsatzes hängt insbesondere von Einsatzort, Verantwortlichem, Zweck, Kamerawinkel, betroffenen Personengruppen und organisatorischem Umfeld ab.

## Aktuelle Projektentscheidung

Für den derzeitigen Forschungs- und Entwicklungsstand gelten folgende feste Grenzen:

- **Temporäre interne Person-IDs bleiben erhalten.** Sie dienen nur dazu, Tracks und Durchgänge technisch zusammenzuführen. Sie werden nicht mit Namen, Konten, Mitarbeiter-IDs oder anderen realen Identitäten verknüpft.
- **OSNet ReID bleibt vorerst aktiv.** Es wird ausschließlich zur kameraübergreifenden Wiedererkennung und zur Vermeidung von Doppelzählungen eingesetzt.
- **Gesichtserkennung wird nicht eingebaut.**
- **Alters-, Geschlechts-, Emotions-, Ethnie- oder ähnliche Personenklassifizierung wird nicht eingebaut.**
- **Keine dauerhafte Video- oder Einzelbildspeicherung.**
- **Keine dauerhafte Speicherung von OSNet-Embeddings.**

Damit bleibt die für die Zählung gewünschte technische Person-ID erhalten, während Funktionen entfallen, die für den Zählzweck nicht erforderlich sind.

## Rechtliche Einordnung

Lokale Verarbeitung macht ein Kamerasystem nicht automatisch DSGVO-konform. Bereits das Erfassen und automatisierte Auswerten identifizierbarer Personen kann eine Verarbeitung personenbezogener Daten darstellen. Maßgeblich bleiben insbesondere Rechtmäßigkeit, Zweckbindung, Datenminimierung, Speicherbegrenzung, Transparenz, Sicherheit und Datenschutz durch Technikgestaltung.

OSNet-ReID ist rechtlich sensibler als reine Detection und Zonenlogik. Das System erzeugt Merkmalsvektoren, um dieselbe unbekannte Person erneut zuzuordnen. Ob dies im konkreten Einsatz als biometrische Verarbeitung im Sinne von Art. 4 Nr. 14 und Art. 9 DSGVO einzuordnen ist, muss für den tatsächlichen Einsatz geprüft werden. Deshalb behandeln wir ReID technisch konservativ als besonders schutzbedürftige personenbezogene Merkmalsverarbeitung.

## Person-ID

`global_person_id` ist eine **interne pseudonyme Laufzeitkennung**, keine reale Identität. Sie darf nicht verwendet werden, um festzustellen, wer eine Person ist.

Aktuelle technische Zielregel:

- ID nur innerhalb des Zählsystems verwenden,
- keine Namens- oder Kontozuordnung,
- keine Gesichtsdaten verknüpfen,
- keine öffentliche Anzeige der ID,
- keine ID in normalen Logs,
- keine dauerhafte Personenhistorie im Standardbetrieb,
- aktuelle Cache-Grenze: maximal 1800 Sekunden,
- ID/Embedding nach Ablauf aus dem Arbeitsspeicher entfernen.

Die 1800 Sekunden bleiben auf Wunsch zunächst bestehen und werden später anhand der realen Messreihe auf Erforderlichkeit geprüft.

## OSNet ReID

OSNet bleibt als technische Kernfunktion erhalten. Schutzmaßnahmen:

- Embeddings ausschließlich im RAM,
- keine Speicherung in SQLite, Logs, Exporten oder Bilddateien,
- kein Training auf den im Produktivbetrieb beobachteten Personen,
- keine Verwendung zur Namensidentifikation,
- kein Aufbau einer dauerhaften Referenzdatenbank,
- Verwendung nur für Cross-Camera-Matching und Doppelzählungsvermeidung,
- automatische Löschung mit dem Identity-Cache.

Falls eine spätere rechtliche Prüfung OSNet für einen bestimmten Einsatzort ausschließt, bleibt als technische Alternative ein Matching über Zeit, Reihenfolge, Bewegungsrichtung, Position und Passage-Geometrie verfügbar. OSNet wird deshalb nicht aus dem Forschungsprojekt entfernt.

## Bewusst ausgeschlossene Funktionen

Folgende Funktionen gehören nicht zum Produktziel und sollen auch künftig nicht stillschweigend ergänzt werden:

- Gesichtserkennung / Face Recognition,
- Zuordnung zu Namen oder Benutzerkonten,
- Altersschätzung,
- Geschlechtsklassifizierung,
- Emotionserkennung,
- Ethnie-/Herkunftsklassifizierung,
- Gesundheits- oder Verhaltensprofiling,
- dauerhafte Bewegungsprofile einzelner Personen.

Diese Funktionen würden für den eigentlichen Zählzweck keinen notwendigen Mehrwert liefern.

## Aufnahme und Bilddaten

- Rohframes nur für Decoding, Detection, Tracking und ReID verwenden.
- Keine permanente Video- oder Snapshot-Speicherung.
- Kein Audio erfassen.
- Vorschau standardmäßig aus.
- Bei bewusster lokaler Vorschau möglichst anonymisieren.
- Öffentliche Wege, Nachbargrundstücke, Arbeitsplätze oder andere unnötige Bereiche durch Kameraposition und Masken minimieren.

## Datenbank und Logs

Standardbetrieb:

- aggregierte Ein-/Ausgangszähler,
- System- und Kamerahealth,
- keine Rohbilder,
- keine persistenten OSNet-Embeddings,
- keine Person-IDs in normalen Logs,
- granulare Personenereignisse standardmäßig deaktiviert.

Werden für Forschung vorübergehend Ereignisse gespeichert, benötigen sie einen getrennten Forschungszweck, kurze Aufbewahrung, Verschlüsselung und eine eigene Freigabe.

## Transparenz

Der tatsächliche Betreiber muss den Kamerabereich und die Verarbeitung transparent kennzeichnen. Die Anwendung erzwingt deshalb vor Produktivstart weiterhin dokumentierte Felder für Zweck, Rechtsgrundlage, Verantwortlichen, Kontakt und bestätigten Datenschutzhinweis.

Die Information sollte wahrheitsgemäß erklären:

- kamerabasierte Personenzählung,
- lokale KI-Verarbeitung,
- temporäre interne Person-ID,
- OSNet-Wiedererkennung zur Doppelzählungsvermeidung,
- keine Gesichtserkennung,
- keine Namensidentifikation,
- keine dauerhafte Bildspeicherung.

## Datenschutz-Folgenabschätzung

Je nach Einsatz kann eine Datenschutz-Folgenabschätzung nach Art. 35 DSGVO erforderlich sein. Die Software darf deshalb nicht pauschal behaupten `DSGVO-konform` oder `DSFA nicht erforderlich`. Vor echtem Einsatz muss eine konkrete Standortprüfung erfolgen.

## Technische Privacy Gates

Vor Kamerastart müssen mindestens folgende Punkte erfüllt sein:

1. Privacy-Modus aktiv.
2. Verarbeitung lokal.
3. Externe Telemetrie deaktiviert.
4. Videoaufzeichnung deaktiviert.
5. Zweck und Rechtsgrundlage dokumentiert.
6. Verantwortlicher und Kontakt dokumentiert.
7. Datenschutzhinweis bestätigt.
8. Remote-API außerhalb Loopback nur mit Authentifizierung und TLS.
9. OSNet-Embeddings nicht persistent.
10. Keine Gesichtserkennung oder demografische/Emotion-Klassifizierung.
11. Keine Secrets in Repository oder Logs.
12. Kamerasichtbereich vor Ort geprüft.

## Für Jugend forscht

Die datenschutzrechtliche Abwägung wird als Teil der Forschungsarbeit dokumentiert. Besonders interessant ist der messbare Vergleich zwischen:

- Detection + Tracking,
- Detection + Tracking + OSNet,
- verschiedenen ReID-Zeitfenstern,
- unterschiedlichen Kamera-/Zonen-Konfigurationen.

Dabei werden Genauigkeitsgewinn und zusätzlicher Datenschutzaufwand gegenübergestellt.

## Offene Abnahme

Vor einem realen produktiven Einsatz müssen Kamerawinkel, Sichtbereich, Personengruppen, Rechtsgrundlage, Hinweisschild, tatsächliche Speicherfristen und die Erforderlichkeit von OSNet am konkreten Ort bewertet werden.

Bis dahin gilt: **OSNet und temporäre Person-IDs sind technisch vorgesehen, aber daraus folgt keine pauschale DSGVO-Konformitätszusage.**
