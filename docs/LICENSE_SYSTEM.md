# Lizenz- und Entitlement-System

Das Projekt besitzt einen expliziten Startschutz. Er ist absichtlich auditierbar und nicht als versteckte Netzwerkfunktion implementiert.

## Ablauf

Vor dem produktiven Service-Start wird eine lokal installierte, signierte Lizenz geprüft. Die GUI bleibt ohne Lizenz für Einrichtung, Import und Diagnose verfügbar und zeigt den Zustand verständlich an.

Optional kann der Herausgeber zusätzlich eine signierte Online-Freischaltung auf GitHub verlangen. Der Paketstandard 1.0 verwendet bewusst die lokale Prüfung; der Online-Check ist nur eine explizit konfigurierbare Zusatzstufe.

Wenn die Zusatzstufe aktiv ist, müssen beide Dokumente mit demselben Ed25519-Schlüssel signiert sein und dieselbe `license_id` enthalten. Eine fehlende, deaktivierte, abgelaufene, fremde oder ungültige Lizenz blockiert ausschließlich den Produktionsdienst.

Der Hardware-freie Emulator und synthetische Tests sind davon getrennt, damit Entwicklung und CI ohne Produktivlizenz möglich bleiben.

## Transport

Die Onlineprüfung akzeptiert ausschließlich HTTPS zu `github.com`, `api.github.com` oder `raw.githubusercontent.com`. TLS verschlüsselt HTTP-Pfad, Header und Inhalt auf dem Transportweg. Netzwerkbeobachter können je nach Netzwerk/DNS/TLS-Konfiguration weiterhin erkennen, dass eine Verbindung zu GitHub aufgebaut wird; GitHub selbst sieht die Anfrage. Eine eigene Verschleierungsschicht wäre kein verlässlicher Sicherheitsgewinn.

## Signatur statt bloßer Dateiexistenz

Nur die Existenz einer Datei wäre leicht kopier- oder manipulierbar. Daher wird zusätzlich eine Ed25519-Signatur geprüft. Der private Signierschlüssel bleibt ausschließlich beim Projektinhaber und darf weder auf dem Pi noch im Repository liegen. Auf dem Pi befindet sich nur der öffentliche Schlüssel.

Beispieldokument vor der Signatur:

```json
{
  "product": "PersonenZ-hler",
  "license_id": "jf-001",
  "enabled": true,
  "issued_at": "2026-08-09T18:00:00Z",
  "expires_at": null,
  "machine_fingerprints": ["sha256:..."]
}
```

## Einrichtung

Fingerabdruck des Zielgeräts anzeigen:

```bash
PYTHONPATH=src python -m visitor_counter.license_guard
```

Schlüsselpaar auf einem vertrauenswürdigen Rechner erzeugen:

```bash
python scripts/license_tool.py generate-keys \
  --private /secure/location/license_private.pem \
  --public config/license_public_key.pem
```

Lizenzvorlage erzeugen und signieren:

```bash
python scripts/license_tool.py template \
  --out /tmp/license-template.json \
  --license-id jf-001 \
  --fingerprint 'sha256:GERAETE_FINGERPRINT'

python scripts/license_tool.py sign \
  --in /tmp/license-template.json \
  --private /secure/location/license_private.pem \
  --out config/license.json
```

Dasselbe signierte Dokument kann unter einem eindeutig gewählten Pfad in einem GitHub-Repository als Online-Freischaltung liegen.

Die Anwendung importiert die lokale Lizenz grafisch nach `/etc/personenzaehler/license.json`. Eine optionale Herausgeberkonfiguration kann in der geschützten Service-Umgebung folgende Werte setzen:

```text
VISITOR_COUNTER_LICENSE_URL=https://raw.githubusercontent.com/OWNER/REPO/BRANCH/licenses/jf-001.json
VISITOR_COUNTER_LICENSE_TIMEOUT=5
VISITOR_COUNTER_LICENSE_FILE=/etc/personenzaehler/license.json
VISITOR_COUNTER_LICENSE_PUBLIC_KEY=/usr/share/personenzaehler/license_public_key.pem
```

Der paketierte systemd-Dienst setzt für den Standardbetrieb:

```text
VISITOR_COUNTER_LICENSE_REQUIRED=1
VISITOR_COUNTER_LICENSE_ONLINE_REQUIRED=0
```

## Sperren und Freigeben

- **Freigeben:** gültige signierte Datei am konfigurierten GitHub-Pfad bereitstellen.
- **Sperren:** Datei entfernen oder `enabled` auf `false` setzen und neu signieren.
- **Ablaufdatum:** `expires_at` auf einen ISO-8601-Zeitpunkt setzen und neu signieren.
- **Gerätebindung:** `machine_fingerprints` auf einen oder mehrere erlaubte Fingerprints begrenzen.

Bei explizit aktiviertem Online-Check wird ein HTTP-404 als nicht vorhandene Freischaltung behandelt und blockiert den Produktionsdienst.

## Grenzen

Das ist ein wirksamer Schutz gegen versehentliche oder einfache unberechtigte Weitergabe, aber kein unknackbarer DRM-Mechanismus. Wer vollständigen Schreibzugriff auf unverpackten Python-Quellcode besitzt, kann prinzipiell Prüfcode verändern. Eine spätere Härtung kann signierte Releases, read-only Deployment, Secure Boot/TPM-ähnliche Bindung oder kompilierte Komponenten ergänzen.
