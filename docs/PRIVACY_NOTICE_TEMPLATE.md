# Datenschutz-Hinweis für kamerabasierte Personenzählung

**Vorlage für den Aushang am Erfassungsbereich**  
**Stand:** 18. August 2026

> **Wichtig:** Diese Vorlage muss vor dem Einsatz ausgefüllt und fachlich/rechtlich geprüft werden. Sie ist keine Rechtsberatung. Der Hinweis sollte gut sichtbar **vor** dem Erfassungsbereich angebracht werden, sodass betroffene Personen ihn wahrnehmen können, bevor sie den Bereich betreten.

---

# 📷 Kamerabasierte Personenzählung

## Kurzinformation – erste Informationsebene

**In diesem Bereich wird eine lokale, kamerabasierte Personenzählung eingesetzt.**

Die Kamerabilder werden zur automatisierten Erkennung von Personen verarbeitet, um Ein- und Austritte bzw. die Auslastung eines Bereichs zu zählen.

| Information | Angabe |
| --- | --- |
| **Verantwortlicher** | `[Name/Firma/Organisation]` |
| **Anschrift** | `[Anschrift]` |
| **Kontakt** | `[E-Mail / Telefon]` |
| **Zweck der Verarbeitung** | `[z. B. Ermittlung der aktuellen Auslastung / Besucherzählung]` |
| **Rechtsgrundlage** | `[Ergebnis der dokumentierten rechtlichen Prüfung]` |
| **Berechtigtes Interesse, falls zutreffend** | `[konkret beschreiben]` |
| **Speicherung von Videos/Einzelbildern** | `Standardmäßig: keine dauerhafte Speicherung` |
| **Granulare Ereignisspeicherung** | `[deaktiviert / aktiviert mit Speicherdauer: ___ Stunden]` |
| **Weitere Datenschutzinformationen** | `[URL eintragen]` |

### QR-Code

**QR-Code zu den vollständigen Datenschutzinformationen:**

> `[QR-CODE HIER EINFÜGEN]`
>
> Ziel-URL: `[https://...]`

---

## Was verarbeitet das System?

Das System verarbeitet Kamerabilder kurzfristig im Arbeitsspeicher, um Personen mittels Computer-Vision-Modell zu erkennen und Zählvorgänge abzuleiten. Im datenschutzfreundlichen Standardbetrieb werden keine Videoaufnahmen oder Einzelbilder dauerhaft gespeichert.

Das System ist nicht für Gesichtserkennung oder die Identifizierung namentlich bestimmter Personen vorgesehen. Es werden standardmäßig keine Namen und keine dauerhaften biometrischen Gesichtsdaten gespeichert.

Die Verarbeitung erfolgt im vorgesehenen Standardbetrieb lokal auf dem eingesetzten Raspberry-Pi-/Hailo-System. Eine Übertragung von Kamerabildern an einen Cloud-Dienst ist für die Laufzeitverarbeitung nicht vorgesehen.

---

# Vollständige Datenschutzinformation – zweite Informationsebene

## 1. Verantwortlicher

**Verantwortlicher gemäß Art. 4 Nr. 7 DSGVO:**

`[Name/Firma/Organisation]`  
`[Straße und Hausnummer]`  
`[PLZ Ort]`  
`[E-Mail]`  
`[Telefon]`

**Datenschutzbeauftragter, falls vorhanden:**  
`[Name/Kontaktdaten oder „nicht bestellt / nicht erforderlich“]`

---

## 2. Zweck der Verarbeitung

Die kamerabasierte Verarbeitung erfolgt ausschließlich für folgenden Zweck:

`[konkreten Zweck eintragen, z. B. Ermittlung der aktuellen Besucherzahl zur Auslastungssteuerung]`

Die gewonnenen Daten dürfen nicht ohne erneute rechtliche Prüfung für andere Zwecke, insbesondere nicht zur Leistungs- oder Verhaltenskontrolle einzelner Personen, verwendet werden.

---

## 3. Rechtsgrundlage

Die konkrete Rechtsgrundlage muss vor der Inbetriebnahme anhand des tatsächlichen Einsatzes bestimmt werden.

**Rechtsgrundlage:**  
`[z. B. Art. 6 Abs. 1 lit. f DSGVO nach dokumentierter Interessenabwägung / andere Rechtsgrundlage]`

**Berechtigtes Interesse, falls Art. 6 Abs. 1 lit. f DSGVO verwendet wird:**  
`[konkretes Interesse beschreiben]`

Eine Einwilligung darf nicht pauschal als Rechtsgrundlage angegeben werden. Falls im konkreten Fall tatsächlich eine Einwilligung erforderlich ist, muss sie freiwillig, informiert, nachweisbar und widerrufbar sein und vor Beginn der betreffenden Verarbeitung vorliegen.

---

## 4. Kategorien verarbeiteter Daten

Je nach aktivierter Konfiguration können insbesondere folgende Daten verarbeitet werden:

- kurzfristige Kameraframes für die lokale Personenerkennung,
- erkannte Personenpositionen und technische Tracking-Informationen während der Verarbeitung,
- aggregierte Zählwerte wie Eintritte, Austritte und aktuelle Belegung,
- technische Status- und Diagnosedaten,
- bei optional aktivierter Ereignisspeicherung zusätzlich pseudonymisierte Ereignisdaten wie Zeitpunkte, Richtung, technische IDs und Konfidenzwerte.

Im vorgesehenen Standardbetrieb werden keine Namen und keine dauerhaften Gesichtsbilder gespeichert.

---

## 5. Empfänger und Übermittlung

**Empfänger der Daten:**  
`[z. B. ausschließlich intern berechtigte Administratoren / Betreiber]`

**Übermittlung an Dritte:**  
`[keine / konkret angeben]`

**Übermittlung in Drittländer außerhalb EU/EWR:**  
`Im vorgesehenen lokalen Standardbetrieb: keine.`

Falls der Betreiber zusätzliche Netzwerk-, Cloud-, Fernwartungs- oder Analysedienste einbindet, ist diese Angabe entsprechend anzupassen und die Zulässigkeit gesondert zu prüfen.

---

## 6. Speicherdauer

Im datenschutzfreundlichen Standardbetrieb:

- keine dauerhafte Speicherung von Videos oder Einzelbildern,
- nur kurzfristige Verarbeitung von Kameraframes für die Inferenz,
- Speicherung aggregierter Zählwerte,
- granulare Personenereignisse standardmäßig deaktiviert.

Falls granulare Ereignisse aktiviert werden:

**Speicherdauer:** `[___ Stunden / Tage]`

Die Projektkonfiguration sieht für aktivierte Ereignisse eine kurze Aufbewahrung und automatische Löschung vor. Die tatsächliche Speicherdauer muss auf das für den jeweiligen Zweck erforderliche Minimum begrenzt werden.

---

## 7. Pflicht zur Bereitstellung der Daten

`[Beschreiben, ob und in welcher Form betroffene Personen den überwachten Bereich vermeiden können. Bei öffentlich zugänglichen Bereichen entsprechend konkretisieren.]`

---

## 8. Automatisierte Entscheidungen

Das System zählt Personen automatisiert. Es ist nicht dafür vorgesehen, Entscheidungen mit rechtlicher Wirkung oder vergleichbar erheblicher Beeinträchtigung über einzelne Personen zu treffen.

**Abweichender Einsatz:** `[falls zutreffend beschreiben]`

---

## 9. Rechte betroffener Personen

Betroffene Personen können – soweit die jeweiligen gesetzlichen Voraussetzungen erfüllt sind – insbesondere folgende Rechte geltend machen:

- Auskunft nach Art. 15 DSGVO,
- Berichtigung nach Art. 16 DSGVO,
- Löschung nach Art. 17 DSGVO,
- Einschränkung der Verarbeitung nach Art. 18 DSGVO,
- Datenübertragbarkeit nach Art. 20 DSGVO, soweit anwendbar,
- Widerspruch nach Art. 21 DSGVO, insbesondere bei einer Verarbeitung auf Grundlage von Art. 6 Abs. 1 lit. f DSGVO.

Anfragen können an den oben genannten Verantwortlichen gerichtet werden.

Da das System im datenschutzfreundlichen Standardbetrieb keine unmittelbare Identifikation von Personen vorsieht, kann eine Zuordnung einzelner gespeicherter Zähl- oder Ereignisdaten zu einer bestimmten natürlichen Person technisch nicht oder nur eingeschränkt möglich sein.

---

## 10. Beschwerderecht

Betroffene Personen haben das Recht, sich bei einer Datenschutzaufsichtsbehörde zu beschweren.

**Zuständige Aufsichtsbehörde:**  
`[Name und Kontakt/URL der zuständigen Datenschutzaufsichtsbehörde]`

---

## 11. Weitere Informationen zum eingesetzten System

Technische Datenschutz- und Sicherheitsdokumentation des Projekts:

- [`DSGVO_DOKUMENTATION.md`](DSGVO_DOKUMENTATION.md)
- [`PRIVACY_AND_SECURITY.md`](PRIVACY_AND_SECURITY.md)

---

## Druck- und Einsatzhinweise für den Betreiber

1. Alle Platzhalter in eckigen Klammern vollständig ersetzen.
2. Die erste Informationsebene gut sichtbar **vor** dem Erfassungsbereich anbringen.
3. Die vollständige Information über URL/QR-Code leicht erreichbar bereitstellen.
4. Kameras so ausrichten oder maskieren, dass nur der für den Zweck erforderliche Bereich erfasst wird.
5. Rechtsgrundlage und ggf. Interessenabwägung dokumentieren.
6. Prüfen, ob eine Datenschutz-Folgenabschätzung nach Art. 35 DSGVO erforderlich ist.
7. Speicherdauer, Zugriffsrechte und Löschfunktion vor Inbetriebnahme testen.
8. Änderungen an Kamerawinkel, Zweck, Speicherumfang, Re-ID, Remotezugriff oder Ereignisspeicherung erneut datenschutzrechtlich bewerten.

### Maßgebliche Orientierung

Für kamerabasierte Verarbeitung sind insbesondere die DSGVO sowie die Leitlinien 3/2019 des Europäischen Datenschutzausschusses zur Verarbeitung personenbezogener Daten durch Videogeräte und die Orientierungshilfen der deutschen Datenschutzaufsichtsbehörden zu berücksichtigen.
