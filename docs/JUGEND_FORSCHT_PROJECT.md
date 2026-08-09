# Jugend forscht – Projektdokumentation PersonenZähler

## 1. Projektidee

Ziel ist ein lokal arbeitender, datenschutzorientierter Personenzähler für Ein- und Ausgänge. Zwei WLAN-Kameras beobachten unterschiedliche Bereiche eines Durchgangs. Ein Raspberry Pi 5 verarbeitet die Videoströme lokal. Ein Hailo-10H beschleunigt die Personenerkennung und ReID-Inferenz. Das System soll Personen zuverlässig zählen, ohne Gesichter zu erkennen, Namen zuzuordnen oder Videomaterial dauerhaft zu speichern.

Die wissenschaftliche Kernfrage lautet:

> Wie zuverlässig kann ein kostengünstiges Edge-AI-System mit zwei Kameras Personen zählen, Doppelzählungen vermeiden und gleichzeitig die Menge dauerhaft gespeicherter personenbezogener Daten minimieren?

## 2. Technisches Konzept

Die Verarbeitungskette ist:

`WLAN-Kamera -> RTSP -> Decoder -> YOLO26m Detection -> lokales Tracking -> OSNet ReID -> globale Identitätslogik -> A/neutral/B-Hysterese -> Dual-Camera-Consensus -> anonyme Zählwerte`

YOLO26m erkennt ausschließlich die Klasse `person`. Das Tracking hält lokale Bewegungsverläufe innerhalb einer Kamera stabil. OSNet liefert temporäre Merkmalsvektoren, um eine Person nach einem Kamerawechsel wiederzuerkennen. Die eigentliche Zählentscheidung wird nicht allein durch das neuronale Netz getroffen, sondern durch eine deterministische Zustandslogik mit Bewegungsrichtung, Zonenfolge, Zeitfenster und Plausibilitätsprüfung.

## 3. Hardware

Geplante Zielhardware:

- Raspberry Pi 5 als zentraler Server
- Hailo-10H mit 8 GB Gerätespeicher als KI-Beschleuniger
- zwei WLAN-/IP-Kameras mit RTSP
- eigener lokaler Router für Kameras, Pi und Displays
- zwei Displays: Belegung und Systemstatus

Die genaue Hardwarekonfiguration, Leistungsaufnahme, Temperatur und reale Inferenzgeschwindigkeit werden erst bei verfügbarer Hardware gemessen und in die Versuchsdokumentation übernommen.

## 4. Warum zwei Kameras?

Eine einzelne Kamera kann Personen zählen, hat aber Probleme bei Verdeckung, Umkehrbewegungen und Personen, die dicht hintereinander laufen. Zwei Kameras liefern zusätzliche zeitliche und räumliche Information. Dadurch kann geprüft werden, ob ein Ereignis physikalisch plausibel ist und ob dieselbe Person an der zweiten Kamera wieder erscheint.

Die zweite Kamera ist keine Sicherheitskamera im klassischen Sinn. Ihr Zweck ist die technische Absicherung des Zählvorgangs.

## 5. Datenschutz als Forschungsbestandteil

Datenschutz ist nicht nur eine Nebenanforderung, sondern ein eigener Teil des Projekts. Verglichen werden sollen verschiedene Betriebsarten:

- reine Detection + Zonenlogik,
- Detection + lokales Tracking,
- Detection + Tracking + kurzlebige ReID,
- unterschiedliche ReID-Zeitfenster.

Zu jeder Variante werden neben der Zählgenauigkeit auch Datenschutzparameter betrachtet: welche Daten entstehen, wie lange sie existieren und ob sie dauerhaft gespeichert werden müssen.

Produktiv sollen keine Videos, keine Einzelbilder und keine ReID-Embeddings dauerhaft gespeichert werden. Persistiert werden primär aggregierte Zählwerte.

## 6. Digital Twin

Da die Zielhardware nicht ständig verfügbar ist, besitzt das Projekt einen Digital-Twin-Emulator. Er ersetzt Kameras, YOLO/Hailo und OSNet durch reproduzierbare synthetische Eingaben, verwendet aber die echte Tracking-, ReID-, Zonen- und Consensus-Logik des Projekts.

Getestete bzw. geplante Szenarien:

- normaler Eintritt und Austritt,
- Umdrehen vor der Linie,
- zwei und mehrere Personen gleichzeitig,
- Verdeckung,
- ähnliche Kleidung,
- Kameraausfall,
- Routerausfall,
- Detektorausfall,
- ReID-Ausfall,
- längere Unterbrechungen,
- variable Bildrate und Frame-Verlust,
- Gegenverkehr,
- dichtes Gedränge.

Damit können logische Fehler vor dem Hardwaretest erkannt werden. Der Emulator ersetzt jedoch keine Messung der realen YOLO-Genauigkeit, WLAN-Stabilität oder Hailo-Geschwindigkeit.

## 7. Verifikation und CI

Das Repository besitzt eine GitHub-Actions-CI. Bei Änderungen werden Python-Dateien kompiliert, Unit-Tests und Digital-Twin-Szenarien ausgeführt. Zusätzlich laufen statische Sicherheitsprüfung, Abhängigkeits-Audit und ein einfacher Secret-Guard. Dependabot prüft regelmäßig Python- und GitHub-Actions-Abhängigkeiten.

Ziel ist, Messfehler und Softwarefehler sauber zu trennen: Ein reproduzierbarer Softwaretest muss zunächst bestehen, bevor reale Kameratests bewertet werden.

## 8. Lokaler KI-Assistent

Als zusätzliche Forschungskomponente wird ein lokaler Projektassistent integriert. Er basiert standardmäßig auf Gemma 4 E2B Instruct und läuft über einen lokalen llama.cpp-Server auf dem Raspberry Pi. Auf Systemen mit mehr RAM kann Gemma 4 E4B getestet werden.

Der Assistent kann:

- Fragen zur Architektur beantworten,
- lokale Dokumentation durchsuchen,
- Diagnosemeldungen erklären,
- kleine Code- oder Konfigurationsänderungen vorschlagen.

Er darf Änderungen nicht autonom anwenden. Jeder Vorschlag wird durch eine deterministische Schutzschicht auf Pfad, Dateityp, Secrets und Versionshash geprüft und benötigt eine ausdrückliche Benutzerbestätigung. Damit lässt sich untersuchen, wie ein generatives Modell sinnvoll in ein sicherheitsrelevantes Edge-System eingebaut werden kann, ohne ihm unbeschränkte Systemrechte zu geben.

## 9. Bedienkonzept

Die Anwendung soll bewusst einfach sein. Der normale Nutzer soll keine technischen Detailparameter verstehen müssen. Vorgesehen sind:

- Startseite mit großem aktuellen Zählwert,
- klare Statusanzeige für beide Kameras und KI,
- Einrichtung als geführter Assistent,
- automatische Kamera- und Streamprüfung,
- Datenschutzprüfung als fester Schritt vor Aktivierung,
- verständliche Fehlermeldungen mit optionalen technischen Details,
- lokale Chat-Hilfe,
- Änderungsvorschläge mit Diff und Rückgängig-Funktion.

Das Design orientiert sich an reduzierten, klaren Oberflächen: wenige Entscheidungen pro Bildschirm, konsistente Begriffe und keine unnötigen Diagnoseinformationen im Hauptpfad.

## 10. Messplan

Für die spätere reale Versuchsreihe werden mindestens folgende Größen erfasst:

- Ground-Truth-Personenbewegungen,
- korrekt erkannte Eintritte/Austritte,
- False Positives,
- False Negatives,
- Doppelzählungen,
- ID-Switches,
- ReID-Fehlzuordnungen,
- End-to-End-Latenz,
- Detektions-FPS,
- CPU- und RAM-Auslastung,
- Hailo-Auslastung,
- Temperatur,
- WLAN-Reconnects und Decodefehler.

Aus den Zählwerten werden Precision, Recall und absolute Zählabweichung berechnet. Für Vergleichstests werden dieselben aufgezeichneten Ground-Truth-Szenarien mit verschiedenen Konfigurationen wiederholt.

## 11. Offene Forschungsfragen

- Wie stark verbessert ReID die Zählgenauigkeit gegenüber Tracking und Zonenlogik allein?
- Wie lang muss der ReID-Cache tatsächlich sein?
- Ab welchem Personendurchsatz nimmt die Genauigkeit deutlich ab?
- Wie robust ist die Zuordnung bei ähnlicher Kleidung?
- Welche Bildrate ist der beste Kompromiss zwischen Genauigkeit und Rechenlast?
- Reicht Gemma 4 E2B als lokaler Support-Assistent oder rechtfertigt E4B den zusätzlichen Ressourcenverbrauch?
- Wie weit lässt sich Datenminimierung treiben, ohne die Zählqualität deutlich zu verschlechtern?

## 12. Dokumentationsprinzip

Ab jetzt werden größere Architekturentscheidungen, Testresultate und verworfene Ansätze dokumentiert. Wichtig ist dabei, klar zwischen drei Kategorien zu unterscheiden:

1. **implementiert und automatisiert getestet**,
2. **implementiert, aber nur auf echter Hardware prüfbar**,
3. **geplant bzw. Hypothese**.

Damit bleibt die Jugend-forscht-Dokumentation nachvollziehbar und reproduzierbar und behauptet keine Messergebnisse, die noch nicht tatsächlich erhoben wurden.
