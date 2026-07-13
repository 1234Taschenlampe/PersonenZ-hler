# Datenschutz- und Sicherheitskonzept

Stand: 13. Juli 2026. Dieses Dokument beschreibt technische Voreinstellungen und offene Betreiberpflichten; es ist keine Rechtsberatung und keine Zusage, dass ein konkreter Einsatz automatisch DSGVO-konform ist.

## Sichere Voreinstellungen

- Inferenz findet lokal auf Raspberry Pi/Hailo statt. Der Laufzeitcode hat keine Cloud-, Analytics- oder Telemetrie-Integration.
- `privacy.enabled`, `local_processing_only` und der systemd-Netzwerk-Namespace sind aktiv; externe Telemetrie ist unzulaessig.
- Die Kameraverarbeitung startet erst, wenn Rechtsgrundlage, Zweck, Verantwortlicher, Kontakt, sichtbarer Hinweis und Zeitpunkt der Betreiberbestaetigung dokumentiert sind.
- Bildvorschau und Remote-Video sind aus. Werden sie bewusst aktiviert, ist fuer Remote-Video Vollbild-Verpixelung vorgeschrieben. Dadurch werden auch Kennzeichen und Gesichter verdeckt, obwohl das Person-only-Modell diese nicht separat erkennt.
- OSNet-Re-ID ist aus. Bei bewusster Aktivierung bleiben Embeddings nur im RAM und verfallen; das rechtliche Risiko ist vorher gesondert zu bewerten.
- Einzelbilder/Videos werden nicht dauerhaft gespeichert. Kurzlebige Streambilder liegen unter Linux bevorzugt in `/dev/shm`, tragen Modus `0600`, gelten maximal drei Sekunden und werden beim Beenden geloescht.
- Granulare Personenereignisse sind aus. Es bleiben nur aggregierte Zaehler. Werden Ereignisse aktiviert, verlangt die Anwendung einen externen Fernet-Schluessel, verschluesselt Textfelder und ersetzt Personen-/Track-IDs durch schluesselgebundene Pseudonyme.
- Ereignisaufbewahrung ist auf 24 Stunden voreingestellt und auf maximal sieben Tage begrenzt. Beim Start und alle fuenf Minuten werden abgelaufene Datensaetze geloescht; SQLite `secure_delete` und WAL-Truncation sind aktiv.
- Logs enthalten keine Bilder. Ein Filter entfernt Track-/Personen-IDs, Bounding-Boxes, Bildkoordinaten und Secrets. Rotation, kurze Dateiaufbewahrung und Dateirechte `0600` sind aktiv.
- Die API bindet an `127.0.0.1`, nutzt keine CORS-Wildcard und fordert getrennte Tokens fuer `viewer`, `operator` und `admin`. Nicht-Loopback-Binding wird ohne TLS plus Authentifizierung verweigert.
- Android verweigert Klartextverkehr, akzeptiert nur HTTPS zu lokalen/privaten Zielen, speichert das Token verschluesselt und sperrt Screenshots/Recent-Task-Vorschauen.
- SSH-Helfer akzeptieren keine unbekannten Hostschluessel und bevorzugen Agent/Schluesseldatei. Passwortauthentifizierung muss explizit freigeschaltet werden.

## Rollen und Funktionen

| Rolle | Zugriff |
| --- | --- |
| oeffentlich | Minimaler Health-Check, Datenschutzhinweis |
| `viewer` | Status, Zaehler, Kamerazustand, WebSocket |
| `operator` | zusaetzlich Telemetrie, Ereignisse, anonymisiertes Video (falls aktiviert) |
| `admin` | zusaetzlich Export und unwiderrufliche Loeschung |

Admin-Export enthaelt nie Bilder. Beispiel:

```bash
curl --cacert /path/ca.crt \
  -H "Authorization: Bearer $VISITOR_COUNTER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit":1000}' \
  https://counter.local:8766/api/v1/privacy/export
```

Loeschung granularer Daten, optional inklusive aggregierter Zaehler:

```bash
curl --cacert /path/ca.crt \
  -H "Authorization: Bearer $VISITOR_COUNTER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"DELETE","reset_aggregates":false}' \
  https://counter.local:8766/api/v1/privacy/delete
```

Beide Aktionen werden ohne IP-Adresse, Token oder Nutzdaten in `logs/audit.jsonl` protokolliert.

## Inbetriebnahme

1. Zweck, Erforderlichkeit, Erfassungsbereich und mildere Mittel dokumentieren. Kameras auf den kleinstmoeglichen Bereich begrenzen und oeffentliche Wege/Nachbarbereiche maskieren.
2. Rechtsgrundlage und Interessenabwaegung bzw. andere Voraussetzungen pruefen. Einwilligung ist bei Videogeraeten laut EDSA nur ausnahmsweise passend; keine Schein-Einwilligung verwenden.
3. Das Muster `PRIVACY_NOTICE_TEMPLATE.md` ausfuellen und den Hinweis vor dem Aufnahmebereich anbringen.
4. `config/config.yaml` ausfuellen: `legal_basis`, `purpose`, `controller_name`, `controller_contact`, `privacy_notice_acknowledged: true` und einen ISO-8601-Zeitpunkt setzen.
5. Secrets ausserhalb des Repositories erstellen:

   ```bash
   sudo install -d -m 0700 /etc/personenzaehler
   sudo .venv/bin/python scripts/generate_secrets.py --output /etc/personenzaehler/api.env
   ```

6. Fuer mobilen Zugriff ein Zertifikat fuer den lokalen Hostnamen aus einer vom Android-Geraet vertrauten CA verwenden, Zertifikat/Key in `api.tls_certificate` und `api.tls_private_key` eintragen und erst dann `api.bind_host` auf eine private Adresse setzen. Der Private Key muss `0600` bleiben.
7. Falls kein Remotezugriff erforderlich ist, API auf Loopback und Video/mDNS deaktiviert lassen.
8. Zugriffsrechte, Loeschung, Wiederherstellung, Hinweisbeschilderung und Kameramasken vor Livebetrieb testen; Pruefung regelmaessig wiederholen.

## Trainingsdaten

Trainingsbilder sind getrennt vom Laufzeitbetrieb zu behandeln. Die Capture/Extract/Hard-Negative-Skripte verlangen jetzt eine externe, befristete JSON-Freigabe mit `approved`, `purpose`, `legal_basis`, `controller` und `expires_at`, einen expliziten Ausgabeordner und private Dateirechte. Rohdaten gehoeren auf ein verschluesseltes, zugriffsbeschraenktes Volume und duerfen nicht in Git, Cloud-Synchronisation oder Backups gelangen. Nach Ablauf sind Bilder, Labels, abgeleitete Crops und Backups gemeinsam zu loeschen.

## DSGVO-Bezug

Die Voreinstellungen unterstuetzen Datenminimierung, Speicherbegrenzung, Integritaet/Vertraulichkeit und Rechenschaftspflicht nach Art. 5 sowie Datenschutz durch Technikgestaltung nach Art. 25 und angemessene Sicherheit nach Art. 32. Transparenz- und Betroffenenpflichten bleiben organisatorisch zu erfuellen. Massgebliche Primaer-/Aufsichtsquellen:

- [DSGVO, insbesondere Art. 5, 6, 13, 15, 17, 20, 25, 30, 32 und 35](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679)
- [EDSA-Leitlinien 3/2019 zur Verarbeitung personenbezogener Daten durch Videogeraete](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_de)
- [DSK-Orientierungshilfe Videoueberwachung](https://www.bfdi.bund.de/SharedDocs/Downloads/DE/DSK/Orientierungshilfen/OH_Video%C3%BCberwachung-n-%C3%B6-Stellen.pdf?__blob=publicationFile&v=5)

## Verbleibende Risiken

- Die Applikationsverschluesselung schuetzt sensible Textfelder und pseudonymisiert IDs, aber nicht SQLite-Header, Zeitpunkte, Richtungen, Confidence-Werte oder aggregierte Zaehler. Bei aktivierter Ereignisspeicherung ist deshalb zusaetzlich Vollvolume-/Datentraegerverschluesselung erforderlich.
- Pseudonyme sind absichtlich nicht direkt auf eine Person rueckfuehrbar. Eine personenspezifische Auskunft kann ohne zusaetzliche, datenschutzrechtlich problematische Zuordnung unmoeglich sein; der Admin-Export ist daher ein Gesamtexport.
- RAM, Prozessspeicher und Kameratreiber enthalten fuer die Inferenz kurzfristig Rohbilder. Ein kompromittiertes Betriebssystem oder privilegierter Angreifer kann darauf zugreifen.
- Vollbild-Verpixelung reduziert das Risiko, garantiert aber nicht gegen jede Rekonstruktionsmethode. Der sicherste Modus bleibt: keine Vorschau, kein Stream.
- Zaehlergebnisse koennen falsch sein. Keine sicherheits-, arbeits- oder personenbezogenen Entscheidungen allein darauf stuetzen.
- Ob eine Datenschutz-Folgenabschaetzung nach Art. 35, ein Verzeichnis nach Art. 30, Arbeitnehmervertretung oder weitere nationale Regeln erforderlich sind, entscheidet der konkrete Einsatz.
- Vorhandene Git-Historie kann alte Artefakte weiterhin enthalten. Sie muss separat bereinigt und alle bereits verteilten Klone/Backups muessen behandelt werden.
- Python- und Android-Abhaengigkeiten sind nicht vollstaendig reproduzierbar gelockt; vor Produktion sind Lockfiles/SBOM, Signatur- bzw. Hashpruefung und ein aktueller Schwachstellenscan in CI erforderlich.
- Die Betreiberfelder in der Konfiguration sind technische Sperren, keine inhaltliche Rechtspruefung. Falsche oder unvollstaendige Angaben koennen vom Code nicht erkannt werden.
