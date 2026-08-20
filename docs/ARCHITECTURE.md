# Architektur der PersonenZähler Desktop Suite

## Leitlinien

Die Anwendung ist eine native PySide6-Desktop-Anwendung für 64-Bit Debian/Raspberry Pi OS. Hailo-10H mit YOLO26m bleibt der einzige produktive Inferenzpfad. Hardwarefreie Daten werden ausschließlich in einem klar markierten Developer-/Testmodus erzeugt.

Die Architektur trennt Darstellung, Application Services und hardwarebezogene Laufzeit. Die GUI greift nicht direkt auf `systemctl`, SQLite-Interna oder Hailo-Bindings zu, sondern verwendet typisierte Dienste mit verständlichen Fehlerobjekten.

## Komponenten

```text
Desktop GUI
  ├─ Übersicht / Ereignisse / Verlauf
  ├─ Kameras / KI & Hardware
  ├─ System / Diagnose
  ├─ Datenschutz & Sicherheit / Lizenz
  ├─ Einstellungen / Über
  └─ First-Run Wizard
           │
Application Services
  ├─ AppState + SettingsService
  ├─ HardwareDiagnostics
  ├─ ServiceManager
  ├─ LicenseService
  ├─ ModelInstallationService + SecurityAssetService
  ├─ DiagnosticBundleExporter
  └─ Event/Statistics queries
           │
Runtime Core
  ├─ Camera Layer: USB/V4L2 + RTSP/HTTP
  ├─ AI Layer: HailoRT + YOLO26m only
  ├─ Tracking/Re-ID: local tracker + optional OSNet/Hailo
  ├─ Counter Engine: crossing, consensus, daily unique, throughput
  ├─ Database: SQLite/WAL, migrations, retention
  ├─ API v1: Android/remote status, events, optional stream
  └─ Privacy/Security: encryption, pseudonyms, auth, redaction
```

## Prozessmodell

Der Produktionszähler läuft unabhängig von der GUI als genau eine Serviceinstanz. Die GUI kann den Dienststatus beobachten und über eine eng begrenzte privilegierte Schnittstelle starten, stoppen oder neu starten. Sie darf keine zweite Produktionspipeline im selben Datenverzeichnis starten.

Im Entwicklungsmodus kann die GUI eine eingebettete Laufzeit oder den digitalen Zwilling verwenden. Dieser Zustand ist sichtbar gekennzeichnet und schreibt nicht in die Produktionsdatenbank.

## Zählsemantik

- `inside`: bestätigte Eintritte minus bestätigte Austritte, nie negativ. Sichtbare Bounding Boxes verändern den Wert nicht.
- `entries`: bestätigte IN-Passagen.
- `exits`: bestätigte OUT-Passagen.
- `throughput`: `entries + exits`.
- `daily_unique`: aktive, datenschutzminimierte Tagesprofile; ohne verlässliche Re-ID als eingeschränkt markieren.
- `suppressed`: als Doppelzählung verworfene Ereignisse.
- `uncertain`: Ereignisse ohne ausreichend sichere Entscheidung.
- `wrong_way`: bestätigte Bewegung entgegen einer konfigurierten Rollen-/Richtungserwartung.

Kameraübergreifende Identität benötigt zeitliche, räumliche und – sofern aktiviert – OSNet-Evidenz. Re-ID nutzt keine Gesichter, Namen oder dauerhafte Identitäten. Tagesprofile werden im RAM gehalten oder optional verschlüsselt bis zum lokalen Tageswechsel persistiert.

## Daten und Pfade

Installierter Betrieb folgt Linux-/XDG-Konventionen:

| Zweck | Systemmodus | Benutzermodus |
|---|---|---|
| Programm | `/usr/lib/personenzaehler` | Development-Checkout |
| Konfiguration | `/etc/personenzaehler` | `$XDG_CONFIG_HOME/personenzaehler` |
| Zustandsdaten/DB | `/var/lib/personenzaehler` | `$XDG_DATA_HOME/personenzaehler` |
| Logs | `/var/log/personenzaehler` | `$XDG_STATE_HOME/personenzaehler/log` |
| Cache/Streamframes | `/var/cache/personenzaehler` | `$XDG_CACHE_HOME/personenzaehler` |
| Lizenz | `/etc/personenzaehler/license.json` | `$XDG_CONFIG_HOME/personenzaehler/license.json` |
| Modelle | `/var/lib/personenzaehler/models` | Projekt-/konfigurierter Pfad |

Eine zentrale Pfadauflösung entscheidet anhand expliziter CLI-Optionen, Installationsmarker und XDG-Variablen. Repository-Pfade bleiben nur im Entwicklungsmodus gültig.

## Konfiguration

YAML bleibt ein serialisierbares Austausch- und Deploymentformat, ist aber nicht das primäre Benutzerinterface. `SettingsService` validiert Änderungen atomar und schreibt über temporäre Datei plus Rename. Secrets werden getrennt von der normalen, GUI-lesbaren Konfiguration gespeichert. Das Paket legt API-/Datenschlüssel in `/etc/personenzaehler/api.env` mit `0640` sowie private TLS-Schlüssel mit restriktiven Rechten ab. Lizenz, HEF, TLS und Konfiguration gelangen ausschließlich über feste, geprüfte PolicyKit-Ziele in den Systemmodus.

## Lizenzmodell

Lizenzdateien sind kanonisch serialisierte, signierte Dokumente. Die Anwendung enthält ausschließlich einen Ed25519-Public-Key. Der private Signierschlüssel und Kundengeheimnisse gehören nicht in dieses Repository oder Paket. Fehlende, ungültige, abgelaufene oder nicht passende Lizenzen erzeugen einen kontrollierten UI-Zustand und blockieren nur den produktiven Betrieb, nicht Lizenzimport und Diagnose.

## Datenschutz und Sicherheit

Sichere Defaults:

- keine Video- oder Bildaufzeichnung;
- Vorschau und Remote-Stream aus;
- granulare Ereignisse aus;
- API an Loopback gebunden;
- Remotezugriff nur mit expliziter Aktivierung, Rollen-Tokens und TLS;
- kurze definierte Retention und automatische Löschung;
- keine Gesichtserkennung oder Namensableitung;
- Diagnoseexport mit zentraler Redaction.

Diese Maßnahmen unterstützen Privacy by Design. Ob ein konkreter Einsatz rechtmäßig ist, bleibt eine Betreiberentscheidung; Dokumentation und GUI behaupten keine pauschale DSGVO-Konformität.

## Fehler- und Nebenläufigkeitsmodell

Langlaufende Hardware-, Kamera-, Dienst- und Diagnoseaktionen laufen in Qt-Workern beziehungsweise getrennten Runtime-Threads. Fehler werden als Code, verständliche deutsche Meldung und optionale technische Details transportiert. Tracebacks gehen in redigierte Logs, nicht als einzige Rückmeldung an Benutzer.

SQLite-Zugriffe bleiben transaktional und thread-synchronisiert. Der Runtime-Service ist einziger Schreiber für Live-Zählereignisse; GUI und API verwenden kurze Leseverbindungen oder Application-Services.

## Kompatibilität

Die bestehende Android-App bleibt auf `/api/v1` kompatibel. Neue Felder werden additiv eingeführt. Bestehende REST-, WebSocket-, Event- und optionale Videoendpunkte behalten Bedeutung und Authentifizierung. Brechende Änderungen erfordern später `/api/v2` statt stiller Änderung von v1.

## Packaging

Das Debian-Paket installiert Python-Anwendung, Desktop-Datei, Icon, Standardkonfiguration, systemd-Einheiten und eine eng begrenzte PolicyKit-Aktion. HailoRT, Firmware und gerätespezifische Herstellerpakete werden geprüft, aber nicht durch eine CPU-Lösung ersetzt oder unehrlich gebündelt. Ein AppImage ist wegen Systemtreiber, HailoRT, V4L2-Gruppen und Serviceintegration höchstens ein experimenteller GUI-Client, nicht das primäre Produktionspaket.
