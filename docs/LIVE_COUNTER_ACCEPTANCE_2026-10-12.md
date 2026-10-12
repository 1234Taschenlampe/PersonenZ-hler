# Übersicht: gespeicherte Belegung und aktuelle YOLO-Erkennungen

Die Übersicht trennt diese Quellen:

- **Aktuell im Gebäude:** der gespeicherte Belegungsstand in `global_counts`.
  Bestätigte Ein-/Austritte verändern ihn. Er wird nicht aus Sichtbarkeit oder
  aus historischen Gesamt-Eintritten minus Gesamt-Austritten neu berechnet.
  Ein Anfangsstand, frühere Korrekturen oder bei null begrenzte Austritte können
  eine Differenz erklären. Ohne vollständige Historie wird deren Ursprung
  nicht behauptet und der vorhandene Stand nicht zurückgesetzt.
- **Aktuell von KI erkannt:** Summe frischer YOLO-Personenerkennungen pro Kamera,
  vor dem Tracking. Dieselbe Person kann in beiden Kameras doppelt enthalten
  sein; diese Kachel behauptet keine eindeutigen Personenidentitäten.
- **Eintritte/Austritte/Durchgänge gesamt:** gespeicherte Gesamtwerte.
  Heutige Passagen werden nur aus ausreichend vollständigen bestätigten
  Ereignisdatensätzen bestimmt. Bei deaktivierter Ereignisspeicherung sind
  Tages-Ein-/Austritte nicht rekonstruierbar und werden nicht als null ausgegeben.
- **Besucher heute (Re-ID):** Tagesprofile in `daily_unique.sqlite3`, mit einem
  ausdrücklichen Hinweis auf die Unsicherheit der Re-ID-Zuordnung.
- **Unterdrückte/unsichere Ereignisse:** Diagnosewerte des Zähldienstes; ohne
  Ereignisspeicherung nicht dauerhaft. Fehlrichtungen sind gespeicherte Werte.

## Aktualisierung und Ausfall

Ein schlanker GUI-Timer liest den gemeinsamen Live-Status alle 400 ms, ohne
Kameraöffnung, Hardwareinferenz, Systemd-Abfragen oder Datenbankzugriff.
Kameraerkennungen verfallen nach zwei Sekunden, einschließlich des Alters
seit dem letzten Status-Write. Pausierte/ausgefallene KI, blockierte Bilder,
unverarbeitete Frames oder ungültige Werte ergeben **Nicht verfügbar**.
Bei einem fehlenden Kamerafeed bleiben dessen Einzelwert und die Gesamtsumme
unverfügbar; der noch aktive Einzelkamerawert bleibt sichtbar.

Die allgemeine Diagnose-/Datenbankaktualisierung bleibt im bestehenden
3-Sekunden-Takt. Der laufende Kamera-/Hailo-Pfad bleibt unverändert.

## Regressionen und Grenzen

Automatisierte Tests prüfen 2→1→0, Ablauf ohne weitere Status-Writes,
Teil-/Totalausfall, pausierte KI, unabhängige gespeicherte Belegung inklusive
Übertrag, read-only Datenzugriff, Tagesgrenzen sowie ausgeschlossene unsichere
und unterdrückte Ereignisse. Der GUI-Test prüft die tatsächlich angezeigten
Werte und Texte. Die physische BOB-Abnahme wird separat in
`/home/admin/VORSTELLUNG_ABNAHME_2026-10-13.md` dokumentiert.

Synthetische GUI-Testdaten beweisen keine realen Personendurchgänge. Der
Live-Zähler zählt Modell-Erkennungen, nicht garantierte tatsächliche Personen.
