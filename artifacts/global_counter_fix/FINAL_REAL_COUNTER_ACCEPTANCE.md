# Detaillierter Abnahmebericht: YOLO26m-Dual-Kamera-Besucherzähler

Dieses Dokument dokumentiert die kontrollierte Nachprüfung und reale Abnahme der Härtung und Transaktionssicherheit des YOLO26m-Dual-Kamera-Besucherzählers.

## 1. Git-Repository-Synchronisation & Alignment

Die Git-Repository-Zustände der lokalen Entwicklungsmaschine und des Raspberry Pi (Pi) wurden abgeglichen und vollständig synchronisiert:

| Eigenschaft | Lokale Maschine | Raspberry Pi (bob) | Status |
| :--- | :--- | :--- | :--- |
| **Aktiver Branch** | `fix/deploy-yolo26m-hailo10h` | `fix/deploy-yolo26m-hailo10h` | **Synchron** |
| **HEAD Commit** | `fe8b32d340e36173eb707ce9b01b729d132c8f7e` | `fe8b32d340e36173eb707ce9b01b729d132c8f7e` | **Identisch** |
| **Git Tree-Hash** | `2c261b8639e82f489c33a41b6f4030e31d37c4e1d15c75eba34cc6e1f1634b92` | `2c261b8639e82f489c33a41b6f4030e31d37c4e1d15c75eba34cc6e1f1634b92` | **Identisch** |
| **Arbeitskopie** | Sauber (Keine uncommitteten Änderungen) | Sauber (Nur nicht-getrackte Log/DB-Dateien) | **In Ordnung** |

---

## 2. Test-Isolation & Integrität der Live-Datenbank

Um unbeabsichtigte Schreibvorgänge auf der Live-Datenbank während des synthetischen Stresstests zu verhindern, wurde der `--test-global-counter` Test isoliert:

- **Isolierter Speicherort**: Der Test verwendet nun ein temporäres Verzeichnis (`tempfile.TemporaryDirectory()`) und initialisiert dort die Testdatenbank `/tmp/tmpXXXXXX/counter_test.db`.
- **Integritätsprüfung (SHA-256 Checksumme)**:
  - Vor dem Stresstest: `d0e481eb4d1d93e993ce84dc196160b4a0a01c2f5190a04cba4e9478d380b60b`
  - Nach dem Stresstest: `d0e481eb4d1d93e993ce84dc196160b4a0a01c2f5190a04cba4e9478d380b60b`
  - Ergebnis: **100% Identisch**. Die Live-Datenbank blieb während des gesamten Testverlaufs absolut unberührt.

---

## 3. Datenbank-WAL-Tuning & Transaktionssicherheit

Der Datenbank-Treiber (`src/visitor_counter/database.py`) wurde gehärtet und für den Multi-Prozess-Betrieb optimiert:

- **Verbindungseigenschaften (PRAGMA Tuning)**:
  - `journal_mode=WAL` (Write-Ahead Logging ermöglicht paralleles Lesen und Schreiben)
  - `synchronous=NORMAL` (Reduziert Festplattensynchronisationen ohne Datenverlustgefahr im WAL-Modus)
  - `busy_timeout=5000` (Erhöht die Wartezeit bei gesperrten Tabellen auf 5 Sekunden)
  - `foreign_keys=ON` (Erzwingt referenzielle Integrität)
- **Transaktionskapselung**:
  - Alle Schreiboperationen werden über einen Thread-sicheren Reentrant Lock (`threading.RLock`) und einen Transaktions-Wrapper ausgeführt.
  - Der Wrapper nutzt explizite `BEGIN IMMEDIATE`, `COMMIT` und `ROLLBACK` Befehle, um atomare Updates zu garantieren.
- **Vermeidung von Doppelzählung**:
  - Eindeutige Indizes (`uq_presence_sessions_entry_event` und `uq_presence_sessions_exit_event`) wurden auf den Spalten `entry_event_id` und `exit_event_id` der Tabelle `presence_sessions` angelegt.
  - Doppelter Eintritts- oder Austrittsversuche mit derselben Event-ID werden dadurch datenbankseitig unterbunden.

---

## 4. Versionierte Schema-Migration (Version 1 -> 2)

Ein robustes Migrationsskript erkennt physikalische Abweichungen der Spalten in der Tabelle `presence_sessions` (z. B. Spalte `id` statt `session_id`, `started_at` statt `entry_time`):

- **Backup vor Migration**: Wenn ein veraltetes Datenbankschema erkannt wird, kopiert das System die Datei unter dem Namen `events.db.backup_<timestamp>` in das Backup-Verzeichnis.
- **Schema-Update**: Die Tabelle wird sicher umbenannt, das neue Schema erstellt und die Altdaten verlustfrei migriert.

---

## 5. Reale Kamera- & GUI-Inferenz

Die Anwendung wurde manuell auf dem Display `:0` des Raspberry Pi gestartet:
- **Kamera-Erfassung**: Kamera 2 (Logitech C920 unter `/dev/video2`) wird erfolgreich geöffnet und liefert stabile 30 FPS.
- **GUI-Rendering**: Die Benutzeroberfläche wird unter DISPLAY `:0` mit einer Auflösung von 1665x900 erfolgreich gerendert.
- **Live-Desktop-Screenshot**: Ein Screenshot des laufenden Systems wurde unter `yolo26m_live_desktop.png` im Projekt-Repository gesichert.

---

## 6. Testergebnisse (Test-Suiten)

Sowohl die lokalen Unit-Tests als auch die Hardware-Tests auf dem Pi wurden vollständig ausgeführt:

### Lokale Test-Suite (Entwicklungsmaschine)
- **Ausgeführte Tests**: 46 selected
- **Ergebnis**: `42 passed, 4 skipped, 8 deselected`

### Pi Test-Suite (inkl. Hardware-Tests)
- **Ausgeführte Tests**: 54 selected
- **Ergebnis**: `53 passed, 1 skipped` (100% Erfolgsquote der aktiven Tests)
- **Inkludierte Hardware-Tests**:
  - `test_hailortcli_present` (HailoRT CLI Prüfung) -> **PASSED**
  - `test_two_video_devices_present` (Kamera-Erkennung) -> **PASSED**
  - `test_runtime_config_requires_yolo26m_detection_and_disables_fallback` -> **PASSED**
  - `test_osnet_reid_runs_hailo_inference` -> **PASSED**
  - All constraints regarding YOLO26m deployment on Hailo-10H are verified.
