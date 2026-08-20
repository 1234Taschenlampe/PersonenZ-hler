# Technisches Security Review

## Prüfbereich

Geprüft wurden aktueller Code und vollständige erreichbare Git-Historie: API/Auth/Rollen, Android-Zugriff, RTSP-/HTTP-Quellen, TLS/CORS, SQLite, Dateipfade, Shell-/Serviceintegration, Lizenzsignaturen, Logs/Diagnose, Backups, Secrets, CI und Paketdateirechte.

## Umgesetzte Maßnahmen

- keine privaten Lizenzschlüssel, produktiven Tokens, Hailo-HEFs oder Kundensecrets im Repository/DEB
- Ed25519-Signaturprüfung mit ausschließlich öffentlichem Verifikationsschlüssel im Paket
- kryptographisch zufällige Viewer-/Operator-/Admin-Tokens und Datenschutzschlüssel bei Installation
- Netzwerkbindung außerhalb Loopback nur bei aktivierter Authentifizierung und TLS
- eng begrenzter PolicyKit-Helfer: feste systemd-Units, feste Datei-/Modellziele, reguläre Dateien, `O_NOFOLLOW`, Größenlimits und atomarer Ersatz
- GUI bleibt unprivilegiert; geschützte Einzelaktionen benötigen Systembestätigung
- `subprocess` ausschließlich mit Argumentlisten, festen Aktionen und ohne Shell-Interpolation
- parameterisierte SQLite-Abfragen, WAL, Sperren, Transaktionen und additive Migrationen
- Diagnoseexport ohne Datenbank/Bilder/Video; rekursive Key-, URL-Credential- und Bearer-Token-Redaktion
- Secrets-Datei `0640`, TLS-Privatschlüssel/Lizenz geschützt, systemd-Härtung mit `NoNewPrivileges`, `ProtectSystem`, `ProtectHome` und begrenzten Schreibpfaden
- Secret-Pattern-Guard und Dependency-/Bandit-Prüfungen in CI

## Historischer Secret-Scan

Der Scan aller erreichbaren Commits fand keine eingecheckten privaten Schlüssel und keine verifizierten produktiven Klartext-Secrets. Treffer auf Begriffe wie `token`, `secret` oder `password` waren Variablennamen, Vorlagen oder Dokumentation. Falls außerhalb der erreichbaren Historie jemals echte Zugangsdaten veröffentlicht wurden, müssen sie unabhängig davon rotiert werden.

## Bewusste Grenzen und Restrisiken

- Python-Quellcode auf einem vollständig kompromittierten Gerät ist modifizierbar; die Lizenz ist Manipulationsschutz, kein unknackbarer DRM-Mechanismus.
- Der öffentliche Konfigurationsanteil ist für die unprivilegierte GUI lesbar. API-Tokens, Datenverschlüsselungsschlüssel und private TLS-Schlüssel liegen separat geschützt. Kamera-URLs mit eingebetteten Passwörtern sollten deshalb vermieden und Kameras in einem isolierten Netz mit dedizierten Minimalrechten betrieben werden.
- Selbst bereitgestellte TLS-Zertifikate und Android-Vertrauensstellung bleiben Betreiberaufgabe; der Pairing-Export liefert einen SHA-256-Fingerabdruck zur Gegenprüfung.
- Sicherheitsupdates für Debian-, Hailo- und Python-Abhängigkeiten müssen regelmäßig eingespielt werden. CI-Berichte ersetzen keine Release- und Zielsystem-Patchstrategie.
- Ein lokaler Administrator kann systembedingt auf Laufzeitdaten zugreifen. Festplattenverschlüsselung, sichere Backups und physischer Schutz sind Deployment-Aufgaben.

## Nicht als Schwachstelle „behoben“

Live-Streaming, Remote-API und granulare Events wurden nicht entfernt. Sie bleiben explizit aktivierbar, sind jedoch standardmäßig aus bzw. auf Loopback begrenzt und durch Auth/TLS, Anonymisierung, Verschlüsselung und Retention abgesichert.
