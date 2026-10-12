# Raspberry Pi: reproduzierbarer Betriebsstand und Hotfix-Abgleich

## Stand und Branch-Abhängigkeiten

Der Abgleich vom 12.10.2026 untersucht die drei heute verwendeten Pi-Checkouts
(`pr18`, `demo`, `livecounter`) sowie die ältere Installation unter `/opt`.
Die Vorführinstallation läuft auf `379e4a7849cc7d5f78a8cecf26550cdd2f86ba2b`.
Ihr Anwendungscode ist sauber; lokale Unterschiede betreffen den importierten
Lizenz-Public-Key, Hailo-Logs und Python-Installationsmetadaten.

- [PR #20](https://github.com/1234Taschenlampe/PersonenZ-hler/pull/20): Kamera-/RTSP-Reconnect, parallele Hailo-Kontexte und korrekte kamerabezogene Latenzen, Zählung auf tatsächlich verarbeiteten Frames, bestätigte Ereigniszeit und Readiness.
- [PR #21](https://github.com/1234Taschenlampe/PersonenZ-hler/pull/21): auf #20 aufgebaut; persistierte Belegung unabhängig von frischen YOLO-Erkennungen, 2-Sekunden-Timeout, Ausfallanzeige, Kamera-Einzelwerte und keine behauptete kameraübergreifende Deduplizierung.
- Der zusätzliche Branch `fix/reproducible-pi-runtime-recovery-20261012` basiert auf #21 und ergänzt die folgenden lokalen Betriebsfixes. Eine spätere Zusammenführung muss die Reihenfolge #20 → #21 → Betriebsfixes erhalten.

Es erfolgt kein Merge nach main und kein Deployment dieses Branches auf die
aktive Vorführung. Die bisherigen Pi-Checkouts, Konfiguration, SQLite-Dateien,
Zählerstände, lokalen Nachweise und Rückfallversionen bleiben erhalten.

## Ursachen und reproduzierbare Lösungen

| Beobachtung | Ursache | Lösung im Repository |
|---|---|---|
| GUI fehlt nach Labwc-Anmeldung | `graphical-session.target` wird dort nicht zwingend aktiviert | `install_autostart.sh` installiert zusätzlich einen XDG-Autostart; `desktop_session.sh` importiert ausschließlich die lokale Desktop-Session und startet die GUI. Kein fester Benutzer, keine feste UID, kein blindes Importieren von SSH-Displays. |
| GUI passt bei geringer HDMI-Auflösung nicht | Früherer Desktop-Modus unter der GUI-Mindestbreite | GUI-Dienst startet maximiert; optionales `configure_preferred_display.py` ermittelt den tatsächlich bevorzugten Monitormodus. Vorhandene kanshi-Konfiguration wird nie überschrieben. Kein festes HDMI-Gerät/Modell/Auflösung. |
| API meldet keine frischen KI-Frames | SQLite und Statusdatei liegen in verschiedenen Verzeichnissen | API und Pipeline verwenden dieselben `RuntimePaths`; explizite Pfad-Overrides bleiben auch bei XDG aktiv. Der SQLite-Pfad ist keine Quelle für den Live-Statuspfad. |
| API startet vor DHCP-Zuweisung | User-`network-online.target` garantiert keine lokale Bind-Adresse | API wartet begrenzt auf ihre konfigurierte IPv4-/IPv6-Adresse, bevor sie den Socket bindet. Auth/TLS bleiben erzwungen. |
| Kameras wechseln ihre DHCP-Adressen | Alte RTSP-Adressen zeigen auf andere oder unerreichbare Geräte | Opt-in MAC-Pinning mit `camera-addresses.json`; Timer prüft erreichbare konfigurierte Ports und begrenzt die Suche auf direkt angeschlossene RFC1918-Netze. Nur ein eindeutiger, erreichbarer MAC-Treffer darf den Host ersetzen. Zugangsdaten, Streamprofil, Port und übrige Einstellungen bleiben erhalten. |
| Kamera-Anmeldung muss in privater URL stehen | Älterer lokaler Patch für Umgebungsvariablen fehlte im aktuellen Source-Pfad | `CameraConfig.username_env/password_env` und Laufzeit-Injektion mit URL-Encoding/IPv6-Unterstützung. Bestehende private URLs bleiben kompatibel. Fehlende Werte erzeugen keine Klartext-Logs. |
| CA wird von Python 3.13 abgelehnt | CA hatte keine kritische `KeyUsage` mit `keyCertSign` | `setup_lan_tls.py` erzeugt eine vollständige CA/Server-Kette mit SAN, SKI/AKI und KeyUsage. `repair-ca` kann dieselbe bestehende CA-Identität mit ihrem privaten Schlüssel neu ausstellen, ohne Server-/API-Schlüssel zu rotieren. Strikter echter TLS-Handshake wird getestet. |
| Lokaler Lizenz-Public-Key wurde im Checkout ersetzt | Individuelle Lizenz passt nicht zum ausgelieferten Prüf-Schlüssel | XDG akzeptiert den separat provisionierten `license_public_key.pem` neben der privaten Konfiguration; explizites `PERSONENZAEHLER_LICENSE_PUBLIC_KEY` hat Vorrang. Git-Dateien müssen nicht verändert werden. |
| Sicherung kopiert inkonsistente WAL-Dateien | Dateikopie laufender SQLite-Dateien ist kein konsistenter Snapshot | `backup_installation.py` nutzt SQLite `backup()` und Integritätsprüfung, sichert private Konfiguration/Dienste sowie Git-Source und lokale tracked Patches. Dienste laufen weiter. |
| Linux-Skripte aus einem Windows-Git-Archiv schlagen fehl | Git `core.autocrlf` exportiert ohne Attributvertrag CRLF, Bash interpretiert `pipefail` mit angehängtem CR | `.gitattributes` erzwingt LF für Shell-/Paket-Launcher; alle Shell-Skripte werden unter Linux auf Syntax geprüft. |

Die alte `/opt`-Installation enthält Änderungen vom 25./26.09., nicht weitere
heutige Anwendungshotfixes. Hailo-10H statt Hailo-8, fehlertoleranter Installer,
User-Service-Verwaltung, Schutz gegen statische Szenen als falsche Verdeckung,
optionale Betreiber-Metadaten und Kamera-Reconnect sind im aktuellen Stand
bereits enthalten bzw. durch umfassendere Implementierungen ersetzt.
Zusätzlich übernommen wurden die fehlenden Kamera-Umgebungszugangsdaten,
Ignore-Regeln für Hailo-/Installations-/Live-Daten und die Start/Stop/Status-Hilfen
mit aktuellen Dienstnamen. Alte feste Kamera-IP-Adressen, falsche Unit-Namen,
ein gerätespezifisch eingebettetes Android-CA-Zertifikat, Zeichensatzfehler und
ein Rückbau technischer Privacy-Schutzregeln werden nicht wieder eingeführt.
`onnxruntime` ist bereits in `requirements-pi.txt` enthalten.

## Frische Installation ohne gerätespezifische Source-Änderungen

Benötigt werden Raspberry Pi 5/ARM64, AI HAT+ 2/Hailo-10H, unterstützter
HailoRT-5.x-Stack, Desktop-Session und erreichbare reale Kameras. Die geprüfte
Vorführung nutzt Debian 13 und Python 3.13; CI prüft zusätzlich 3.11/3.12.
Kein Hailo-8-`hailo-all`, CPU- oder Dummy-Fallback wird zum Ersatz erklärt.

Für einen separaten neuen Checkout den vollständigen Betriebsfix-Branch
auschecken (er enthält seine beiden Vorgänger):

```bash
git clone --branch fix/reproducible-pi-runtime-recovery-20261012 https://github.com/1234Taschenlampe/PersonenZ-hler.git
cd PersonenZ-hler
bash scripts/install_linux_app.sh --dry-run
bash scripts/install_linux_app.sh
export PERSONENZAEHLER_USE_XDG=1
```

Der Installer installiert fehlende Abhängigkeiten, bewahrt einen vorhandenen
Hailo-10H-Stack, lädt die offiziellen YOLO26m-/OSNet-HEFs mit SHA-256-Prüfung,
legt private API-Tokens einmalig an und installiert User-Dienste/Autostart.
Eine notwendige Firmwareaktivierung kann einen bewussten Neustart erfordern.
Die Hailo-Postprocessing-Dateien kommen aus dem Repository. Modellpfade werden
im neuen Checkout konfiguriert/importiert, niemals auf einen alten Checkout
verlinkt. `scripts/download_models.py --check` prüft die benötigten Dateien.

Kameras und Datenschutz über den vorhandenen Assistenten einrichten. Wer
Umgebungszugangsdaten nutzt, setzt pro Kamera nur die Variablennamen
`username_env`/`password_env` in der Konfiguration; die tatsächlichen Werte
gehören in die private `api.env` (0600), welche die User-Dienste laden.
Eine gültige signierte Lizenz und der dazugehörige Public-Key müssen getrennt
bereitgestellt werden. Lizenz-, Authentifizierungs- und Hardwareprüfungen
werden nicht umgangen.

Für DHCP-Recovery legt der Betreiber bei Bedarf privat eine JSON-Zuordnung
von Kamera-ID zu **vorher tatsächlich verifizierter MAC-Adresse** neben
`config.yaml` an. Ohne diese Datei ist der Guard ein No-op. Die Suche umfasst
höchstens 4096 direkt angeschlossene private IPv4-Adressen; unbekannte Geräte
werden nicht mit Kamera-Zugangsdaten ausprobiert. Hostnamen oder DHCP-Reservierungen
sind vorzuziehen. IPv6-Kamera-DHCP-Recovery wird nicht behauptet.

TLS wird ausdrücklich für den eigenen DNS-Namen und die eigenen aktuellen
Adressen provisioniert, beispielsweise mit bereits gesetzten lokalen Variablen:

```bash
.venv/bin/python scripts/setup_lan_tls.py create --output "$PRIVATE_TLS_DIR" --hostname "$PI_DNS_NAME" --address "$PI_LAN_ADDRESS"
```

Ausgabe enthält CA-/Server-Schlüssel und bleibt privat. TLS-Zertifikat und
Server-Schlüssel über die bestehende Sicherheitskonfiguration importieren,
CA auf Clients vertrauen, `bind_host` passend setzen und `require_auth` aktiv
lassen. Der Befehl verändert weder Konfiguration noch laufende Dienste.
Vorhandene Dateien werden nie überschrieben. Eine CA-Reparatur erfolgt mit
`repair-ca --certificate ... --private-key ... --output ...`; das neue
Vertrauenszertifikat muss anschließend bewusst auf Clients importiert werden.

Nach Desktop-Anmeldung startet die GUI automatisch. Optional den realen
bevorzugten Monitormodus mit `configure_preferred_display.py` zunächst anzeigen;
`--apply` schreibt ausschließlich eine **neue** kanshi-Konfiguration. Eine
vorhandene Desktop-Konfiguration wird dadurch nicht geändert.

## Diagnose, private Sicherung und Rückfall

```bash
export PERSONENZAEHLER_USE_XDG=1
bash scripts/show_status.sh
.venv/bin/python scripts/runtime_acceptance.py --seconds 30
.venv/bin/python scripts/backup_installation.py --output "$PRIVATE_BACKUP_DIR"
```

Die Statusprüfung liest Live-Daten und SQLite ausschließlich; sie startet
keinen zweiten Kamera-/Hailo-Prozess. JSON unterscheidet aktuelle rohe
KI-Erkennungen, persistierte Belegung und Zählereignisse. Beobachtete Personen
sind kein Ground-Truth-Nachweis tatsächlich erfolgter Ein-/Austritte.
Start/Stop-Hilfen existieren separat und laufen niemals automatisch als Teil
eines Tests oder Git-Pushs.

Die private Sicherung enthält konsistente Zähler- und Tagesdatenbanken,
Konfiguration, TLS/API/Lizenz-Dateien, relevante User-Units, Desktop-Dateien,
Git-Commit und tracked Änderungen. Untracked lokale Helfer sind separat zu
bewahren. Backups werden außerhalb von Git/Runtime-Verzeichnissen angelegt;
vorhandene Ziele und Symlinks werden abgelehnt. Die Sicherung muss lokal
geschützt bleiben. Zum Code-Rückfall einen bereits geprüften Checkout wählen,
dessen Installation mit derselben privaten Konfiguration verbinden und die
User-Units bewusst aktualisieren. **Produktive SQLite-Dateien nicht durch alte
Backup-Dateien ersetzen.** Kein automatisches Rollback/Deployment während der
Vorführung.

Automatische Source-Updates lassen sich mit der bestehenden Datei
`auto-update.paused` neben der Konfiguration sperren. Der Installer und die
späteren GitHub-Commits heben diese Sperre nicht auf. Der Kamera-Guard repariert
nur Adressen; er deployt keinen Code.

## Tatsächlich durchgeführte Tests und Grenzen

Vor diesem reinen Git-Abgleich liefen auf BOB echte parallele Live-Frames beider
Kameras über Hailo-10H/YOLO26m. OSNet wurde auf dem physischen Beschleuniger
geprüft. Eine öffentliche Mehrpersonen-Testaufnahme wurde mit 240 Frames auf
dem Hailo verarbeitet: maximal 10 Personendetektionen, 9 bestätigte IoU-Tracks,
6 normierte 512-dimensionale OSNet-Embeddings. Das war aufgezeichnetes Video,
keine Live-Bewegungsprüfung. Der tatsächlich aktive Tracker war
`IoUFallbackTracker`; ein aktiver ByteTrack wird nicht behauptet.

Die generische Wiederholung ist `recorded_video_acceptance.py --video ...
--sha256 ... --hardware-test`. Sie verweigert einen laufenden oder nicht sicher
prüfbaren Produktionsdienst, verändert keine Dienste und speichert keine
Aufnahmen/Embeddings/Datenbanken. Die bisher verwendete öffentliche Quelle war
OpenCV `samples/data/vtest.avi`, SHA-256
`45cddc9490be69345cbdab64ca583be65987e864ca408038e648db99e10516cf`.
Die Aufnahme selbst wird nicht ins Repository übernommen.

Frühere Wiederanlauf-/Reconnect-/Recovery- und HDMI-Prüfungen sind in den
geschützten lokalen Abnahmeprotokollen und den Dokumenten der beiden Vorgänger
festgehalten. Der letzte tatsächliche Neustart startete beide Kameras, KI, API
und GUI automatisch ohne Dienst-Restarts und erhielt die Datenbanken. Alle
neun GUI-Seiten wurden auf dem realen HDMI-Desktop bedient. Der Live-Zähler
wurde gegen echte Kameradaten geprüft; bei tatsächlichem Dienstausfall zeigte
er nicht verfügbar und nach Recovery wieder aktuelle Daten.

Für diesen zusätzlichen Branch werden vollständige nicht-hardwareabhängige
Regressionen in einer separaten Pi-Testkopie und CI ausgeführt. Dort sind
systemd-Installer-Aufrufe gemockt, Qt ist offscreen und alle Testdaten sind
temporär. Die neue Version wird **nicht** als bereits live deployt bezeichnet.

**NICHT GETESTET:** kontrollierte 10 Eintritte/10 Austritte je Kamera mit
zugehöriger Person als Ground Truth, reale Mehrpersonen-Passage, Android auf
einem tatsächlich angeschlossenen Gerät und eine vollständige Neuinstallation
dieses neuen Branches auf einem zweiten Pi. Hardwareinferenz, Testvideo und
synthetische Regressionen ersetzen diese Nachweise nicht.

## Bewusst nicht in GitHub enthalten

Private API-/Kamera-Passwörter, Tokens, TLS-/CA-/Lizenz-Privatschlüssel,
individuelle Zertifikate/Pairing-Dateien, gerätespezifischer Lizenz-Public-Key,
signierte lokale Lizenz, Kamera-MACs/Adressen, persönliche Konfiguration,
SQLite-Dateien samt WAL, Live-Status/Logs, Aufnahmen, private Backups und
SSH-Hilfsskripte bleiben lokal. Die allgemeinen Installations- und
Recovery-Mechanismen sind versioniert; die installationsspezifischen Werte
müssen sicher separat provisioniert werden. Rohdaten/Testbilder werden nicht
als öffentliche Testnachweise hochgeladen.
