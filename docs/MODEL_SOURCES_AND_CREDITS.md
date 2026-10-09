# Offizielle Hailo-10H-Modelle – Quellen und Credits

Dieses Projekt lädt die **Original-HEF-Binärdateien direkt bei Hailo** herunter.
Die kompilierten Drittanbieter-Modelle werden **nicht in diesem Git-Repository
weiterverbreitet**. Modellautoren, Modellarchitektur und die Hailo-Kompilierung
sind nicht Eigenentwicklungen dieses PersonenZähler-Projekts.

## 1. YOLO26m – Personendetektion

| Element | Herkunft |
| --- | --- |
| Modellarchitektur und Ursprung | [Ultralytics / ultralytics](https://github.com/ultralytics/ultralytics) |
| Kompilierte Hailo-10H-HEF | [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo/blob/master/docs/public_models/HAILO10H/HAILO10H_object_detection.rst) |
| Hailo-Modellrelease | v5.4.0 / hailo10h / yolo26m |
| Direkter Originaldownload | [yolo26m.hef](https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.4.0/hailo10h/yolo26m.hef) |
| Lokaler Zielname | `models/yolo26m_detection_hailo10h_640.hef` |
| SHA-256 (im bisherigen Projektmanifest hinterlegt) | `f1435f7235c77b05736a5ab01b673cc156a95d85b5126aee7f7eb062ec2b2c66` |
| Eingabe | RGB/NHWC, 640 × 640 |
| Verwendete Klasse | COCO class 0 = person |

**Credits:** Ultralytics (Entwicklung der YOLO-Modellfamilie), Hailo
(Kompilierung und Distribution der Hailo-10H-HEF).

**Lizenz:** Ultralytics erläutert zwei Lizenzwege: AGPL-3.0 für passende
Open-Source-Nutzung oder eine separat zu erwerbende Enterprise-Lizenz für
entsprechende proprietäre Nutzung. Die Lizenzbedingungen sind unabhängig
davon zu prüfen, ob die HEF von Hailo heruntergeladen wird:
<https://www.ultralytics.com/license>.

## 2. OSNet x1.0 – Person Re-Identification

| Element | Herkunft |
| --- | --- |
| Originalimplementierung | [Kaiyang Zhou / deep-person-reid](https://github.com/KaiyangZhou/deep-person-reid) |
| Hailo-kompilierte Versionen | [Hailo Model Zoo – Person Re-ID](https://github.com/hailo-ai/hailo_model_zoo/blob/master/docs/public_models/HAILO10H/HAILO10H_person_re_id.rst) |
| Hailo-10H-Version in unserem bestehenden Manifest | v5.3.0 / hailo10h / osnet_x1_0 |
| Direkter Originaldownload | [osnet_x1_0.hef](https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.3.0/hailo10h/osnet_x1_0.hef) |
| Weitere offizielle Version | [Hailo Model Zoo v5.4.0](https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.4.0/hailo10h/osnet_x1_0.hef) |
| Lokaler Zielname | `models/osnet_x1_0_hailo10h.hef` |
| SHA-256 für v5.3.0 aus dem bisherigen Projektmanifest | `5c376b5e16cc42d8e5511aad649cc74b9503d4f44911a28ab157cbe899db1d39` |
| Eingabe | 256 × 128 RGB/NHWC |
| Embedding | 512 Dimensionen |

**Credits:** Kaiyang Zhou et al. (OSNet / Deep Person Re-ID),
Hailo (Kompilierung für Hailo-10H und Bereitstellung).

**Lizenz:** Die Open-Source-Implementierung `deep-person-reid` steht unter
der MIT-Lizenz ([LICENSE](https://github.com/KaiyangZhou/deep-person-reid/blob/master/LICENSE)).
Für Trainingsgewichte, Datensatznutzung und andere Drittkomponenten können
weitere Bedingungen relevant sein.

Die SHA-256-Prüfsumme ist **versionsgebunden**. Der Installer verwendet
deshalb standardmäßig die v5.3.0-Datei aus dem schon vorhandenen,
historisch dokumentierten Projektmanifest. Die neuere v5.4.0-Datei darf
nicht ohne Prüfung einfach mit der alten SHA-256 oder einer umbenannten
Datei gleichgesetzt werden.

## 3. Hailo-Quellen und Toolchain

- [Hailo Model Zoo](https://github.com/hailo-ai/hailo_model_zoo):
  offizielle HEFs, Modellkonfigurationen, Benchmarks und Referenzlinks
- [Hailo Apps](https://github.com/hailo-ai/hailo-apps):
  Referenzpipeline und Beispiele für Hailo-10H
- [HailoRT](https://github.com/hailo-ai/hailort):
  Runtime/API für die Geräteausführung
- [Hailo Model Zoo LICENSE](https://github.com/hailo-ai/hailo_model_zoo/blob/master/LICENSE):
  Lizenz für den Model-Zoo-Quellcode

Das Hailo Model Zoo selbst ist laut dessen README MIT-lizenziert. Das
überträgt **nicht automatisch** eine MIT-Lizenz auf jedes zugrundeliegende
Drittmodell, dessen Trainingsgewichte oder zusätzliche Abhängigkeiten.

## 4. Originalmodelle installieren

Von der Pi-Desktop-Anwendung: **KI & Hardware** →
**Beide Originalmodelle herunterladen**.

Oder für die Quellcodeinstallation:

```bash
cd ~/.local/share/personenzaehler/app
.venv/bin/python scripts/download_models.py --kind all
.venv/bin/python scripts/download_models.py --check
```

Der Installer:

1. Liest nur die versionierten, offiziellen Hailo-URLs aus
   `models/manifests/*.json`
2. Erlaubt ausschließlich Downloads per HTTPS vom offiziellen
   `hailo-model-zoo.s3.eu-west-2.amazonaws.com`
3. Prüft den kompletten SHA-256-Digest **vor** dem Installieren
4. Überschreibt niemals stillschweigend eine bereits vorhandene,
   abweichende lokale Modelldatei
5. Prüft, soweit HailoRT verfügbar ist, `hailortcli parse-hef` auf HAILO10H

Die im Repository hinterlegten Digests stammen aus den früheren
Projektmanifests; die heruntergeladenen Daten werden auf dem jeweiligen
Pi beim Download erneut gegen diese Referenz geprüft. Die Hashprüfung
ist keine eigenständige Geräteabnahme.

**Wichtig:** Eine heruntergeladene und korrekt gehashte HEF-Datei ist
noch **kein Nachweis**, dass die aktuell installierte HailoRT-Version
das Modell ausführen kann oder dass die Ausgabe-Tensoren zur
Postprocessing-Pipeline passen. Dies erfordert einen tatsächlichen
HailoRT-Inferenz- und Kameratest auf dem Zielgerät. Bei
`HAILO_NOT_IMPLEMENTED` oder inkompatiblen HEF-Versionen ist die
offizielle Treiber-/Firmware-Kombination zu aktualisieren, nicht die
HEF-Datei einfach umzubenennen.

