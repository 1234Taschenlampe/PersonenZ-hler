# Feature- und Historien-Audit

Stand: 2026-08-20  
Untersuchter Ausgangspunkt: `main` / `3ea3a52bf48ccc0fec49af30b730ddc120a1acd0`  
Sicherung: `backup/pre-linux-desktop-suite-20260820`  
Entwicklungszweig: `feature/linux-desktop-suite`

## Umfang und Methode

Untersucht wurden alle 93 erreichbaren Commits vom Initial Commit `a014149` bis zu den Spitzen aller Remote-Branches. Neben Baum, Statistiken und Commit-Nachrichten wurden die tatsächlichen Diffs der Produktions-, Android-, Datenschutz-, Security-, Datenbank-, Kamera-, Hailo-, Re-ID-, Deployment- und GUI-Änderungen sowie alle Löschungen geprüft.

Verwendete Prüfungen umfassten insbesondere:

- `git log --all --graph --decorate --oneline`
- `git log --all --stat` und relevante Patch-Diffs
- `git log --all --full-history --diff-filter=D`
- Vergleiche von `main` mit `feature/daily-unique-throughput` und `feature/wlan-reid-three-zone-v2`
- Quellcode- und Konfigurationsinventar mit `rg`
- Baseline-Testlauf mit `pytest`
- Suche nach credential-typischen Mustern über alle Revisionen; Treffer wurden ohne Ausgabe möglicher Werte ausgewertet

Der Baseline-Testlauf auf Windows/Python 3.12 ist erfolgreich. Vier hardware- oder modellabhängige Tests werden erwartungsgemäß übersprungen. Raspberry Pi, V4L2 und Hailo-10H standen für diesen Audit nicht zur Verfügung.

## Historische Linien

Die Historie enthält drei fachlich relevante Linien:

1. `main` enthält den stabilen Dual-Kamera-/Hailo-Kern, Datenbankmigrationen, die Android-API, Privacy-Hardening und die aktuelle DSGVO-Dokumentation.
2. `feature/daily-unique-throughput` ergänzt ereignisgesteuerte Belegung, Tagesbesucher, Durchfluss, verschlüsselte aktive Tagesprofile und einen ersten Linux-App-Installer.
3. `feature/wlan-reid-three-zone-v2` ergänzt robuste RTSP-/HTTP-Kameras, eine headless Produktionslaufzeit, kreuzungsbasierte Belegung, Hailo-OSNet-Re-ID, Emulator, lokale Diagnosefunktionen, signierte Lizenzen und CI.

Die beiden Feature-Linien sind voneinander abgezweigt und dürfen deshalb nicht durch Auswahl nur einer Linie gegeneinander ausgespielt werden. Die Zielarchitektur integriert die sinnvollen Verträge beider Linien kontrolliert auf Basis von `main`.

## Feature-Matrix

| Feature | aktuell vorhanden | historisch vorhanden | funktionsfähig / Evidenz | Datenschutzrelevanz | Entscheidung | Regressionstest |
|---|---:|---:|---|---|---|---|
| Native PySide6-GUI | ja | ja | Import- und Baseline-Test | mittel | behalten, in modulare moderne Desktop-Shell überführen | GUI-Smoke |
| Duale USB-Kameras | ja | ja | CameraManager- und Pipeline-Tests | hoch | behalten | Kameraquellen-/Multi-Camera-Test |
| RTSP-/HTTP-Kameras | nein | ja | V2-Branch mit Reconnect-Telemetrie | hoch | sicher wiederherstellen; Credentials redigieren | Network-Camera-Test |
| Kameraanzeige ohne Inferenz | ja | ja | Commit `edb1fc1`, Pipeline-Test | hoch | behalten; Vorschau explizit aktivierbar | GUI-/Pipeline-Test |
| Hailo-10H-Detektion | ja | ja | Modell- und Hardwareverträge | gering | unverändert produktiv, fail-closed | Model-/Hardware-Test |
| YOLO26m Person-Filter | ja | ja | Manifest- und Postprocess-Tests | hoch | produktiver einziger Detektor | Model-Test |
| CPU-/Dummy-Fallback | nein | Test-Emulator ja | Konfigurationsschutz vorhanden | hoch | nur expliziter Test-/Emulatormodus | Config-Test |
| Lokales Tracking | ja | ja | Tracker-Tests | hoch | behalten | Tracker-Test |
| Kameraübergreifende Identität | ja | ja | Identity-Tests | hoch | Re-ID-Evidenz verlangen; kurze TTL | Identity-/Multi-Camera-Test |
| OSNet auf Hailo | optional | ja | V2-Hardwarepfad und Statusprüfung | hoch | für Tageszählung explizit aktivierbar, kein Gesicht | Re-ID-Test |
| Aktuell im Gebäude | ja, im Main teils sichtbarkeitsgetrieben | ja, kreuzungsgetrieben | Counter-/DB-Tests | mittel | nur durch bestätigte IN/OUT-Ereignisse ändern | Counter-Test |
| Eintritte/Austritte | ja | ja | Crossing-/DB-Tests | mittel | behalten | Entry-/Exit-Test |
| Tagesbesucher | nein | ja | Daily-Branch mit Roll-over-Test | hoch | wiederherstellen; Memory-first, optional verschlüsselt | Daily-Unique-Test |
| Durchfluss | indirekt | ja | `entered + exited` | gering | als eigener abgeleiteter Wert exponieren | Counter-/API-Test |
| Doppelzählungsunterdrückung | ja | ja | Consensus-/Identity-Tests | hoch | behalten und Re-ID-Evidenz stärken | Consensus-Test |
| Unsichere Ereignisse | ja | ja | Consensus-Test | mittel | separat speichern/anzeigen | Counter-/API-Test |
| Fehlrichtung | teilweise über Richtung/Rolle | konzeptionell ja | kein vollständiger Alarmvertrag | mittel | konfigurierbaren Alarm ergänzen | Counter-/Event-Test |
| SQLite WAL/Transaktionen | ja | ja | Migrations-/DB-Tests | hoch | behalten, Migrationen erweitern | DB-/Upgrade-Test |
| Retention und Löschung | ja | ja | Privacy-Tests | hoch | GUI-bedienbar machen | Retention-/Privacy-Test |
| Verschlüsselte granulare Events | ja | ja | Fernet-/Export-Test | hoch | opt-in und fail-closed | Privacy-Test |
| REST-API v1 | ja | ja | API-/Auth-Tests | hoch | kompatibel halten | API-Test |
| WebSocket-Livestatus | ja | ja | Android-Client und Serverpfad | mittel | authentifiziert behalten | API-/Android-Test |
| Remote-MJPEG | ja, default aus | ja | Android-Historie und Privacy-Hardening | sehr hoch | sichere Default-Aus-Schaltung behalten; explizites Opt-in | API-Privacy-Test |
| Android Dashboard/Monitoring | ja | ja | Android-Quellen und Unit-Tests | hoch | API v1 beibehalten | Parser-/Integrationstest |
| WLAN-Roaming/mDNS | ja | ja | Android-Netzwerkcode und Services | mittel | behalten, Paketpfade portabel machen | Android-Test/Packaging-Test |
| Headless Service | teilweise systemd | ja | V2-`VisitorCounterService` | mittel | wiederherstellen und sauber von GUI trennen | Service-Smoke |
| Serviceverwaltung ohne Terminal | nein | nein | nur Shell/systemctl | gering | GUI + PolicyKit-Helper | Service-Manager-Test |
| First-Run-Assistent | nein | nein | — | sehr hoch | neu implementieren, Abschlusszustand persistent | Wizard-Test |
| Diagnosebericht | einfacher JSON-Bericht | erweitert historisch | Diagnostics-Code vorhanden | hoch | redigiertes Diagnosepaket ergänzen | Redaction-Test |
| Signierte lokale Lizenz | nein in main | ja | V2 Ed25519-Tests | mittel | wiederherstellen; nur Public Key im Paket | License-Test |
| Digitaler Zwilling/Emulator | nein | ja | V2 Unit-Tests | gering | als klar markierten Developer-Modus behalten | Emulator-Test |
| Lokaler Gemma-Agent | nein | ja | V2-Branch | hoch | nicht in produktiven Kern aufnehmen; fachfremd und zusätzliche Angriffsfläche | dokumentiert |
| Debian-Paket | nein | einfacher Installer ja | kein reproduzierbares `.deb` | gering | natives Paket mit Launcher, Icons und Services bauen | Packaging-Test |
| AppImage | nein | nein | Hailo-Systemabhängigkeit verhindert vollständige Bündelung | gering | nur als experimentell dokumentieren, `.deb` priorisieren | — |
| CI | nein auf main | ja | V2 GitHub Actions | gering | modernisiert wiederherstellen | Workflow-/Syntaxprüfung |

## Gelöschte und ersetzte Dateien

- Gelöschte Kamera-/Hailo-Screenshots, Logs und große Artefakte werden nicht wieder in den Produktbaum aufgenommen. Sie sind historische Verifikationsartefakte, keine Laufzeitfunktion.
- YOLO26x-Trainings- und Compile-Helfer wurden beim Wechsel auf YOLO26m entfernt. Die alte Funktion ist technisch durch den verbindlichen YOLO26m/Hailo-10H-Pfad ersetzt; ein produktiver YOLO26x-Fallback wäre ein Rückschritt.
- `docs/DSGVO_DOKUMENTATION.md` wurde auf dem V2-Branch gelöscht. Diese Löschung wird nicht übernommen; die aktuellere Betreiber-Dokumentation bleibt erhalten und wird angepasst.
- Der lokale Gemma-Projektagent wird nicht automatisch reaktiviert. Er ist nicht Teil der Personen-/Kamera-Kernfunktion, erweitert die lokale Angriffsfläche und erfordert eigene Modell- und Betriebsentscheidungen.

## Privacy- und Security-Befund

Der Privacy-Hardening-Commit `9a2e1dc` hat wesentliche Funktionen nicht zerstört, sondern standardmäßig deaktiviert oder abgesichert: Remote-Video, granulare Events, Remote-Bindung, Tokens, TLS, CORS und Retention. Diese sicheren Defaults bleiben erhalten; GUI und Wizard machen explizite Aktivierung und Folgen transparent.

Die Revisionensuche fand viele Quellstellen mit Begriffen wie `token` oder `password`, aber in der geprüften Historie keine als Stringliteral eingecheckten produktiven Zugangsdaten oder privaten Signierschlüssel. Vor jedem Push folgt erneut ein Scannerlauf. Sollten bei erweiterten Scannern später echte historische Secrets erscheinen, wird die Historie nicht automatisch umgeschrieben; Rotation und Fundstelle werden dokumentiert.

Bekannte technische Risiken des Ausgangsstands:

- mehrere systemd-Dateien enthalten feste Benutzer- und Repository-Pfade;
- normale Installation und Administration verlangen Shell-/systemctl-Nutzung;
- GUI und Backend sind eng gekoppelt; `gui.py` ist monolithisch;
- Konfiguration erfolgt primär über YAML;
- die Status-API ist ein eigenes Skript statt ein paketiertes Modul;
- Tageszählung und V2-Funktionen liegen nicht auf `main`;
- ein signiertes Lizenzmodell ist historisch vorhanden, aber nicht integriert;
- keine reproduzierbare Debian-Paketpipeline auf `main`.

## Migrationsentscheidung

1. `main` bleibt fachliche Basis und ist durch einen Remote-Backup-Branch gesichert.
2. Historische Funktionen werden mit erhaltener Git-Abstammung integriert; Konflikte werden gegen die Matrix entschieden.
3. Zählsemantik wird ereignisgesteuert: Sichtbarkeit ist Telemetrie, nicht Belegung.
4. Die GUI wird als modulare Desktop-Shell neu strukturiert, während bestehende Kamera-, Hailo-, DB-, Tracking- und API-Implementierungen weiterverwendet werden.
5. Pfade werden über eine zentrale XDG-/Installationspfadschicht abstrahiert.
6. First-Run, Lizenz, Serviceverwaltung, Diagnose und Einstellungen werden als Application Services implementiert und von GUI-Seiten konsumiert.
7. `.deb`, Desktop-Datei, Icon, systemd-/PolicyKit-Integration und CI werden als normale Projektbestandteile getestet.

