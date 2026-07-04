# Final YOLO26x Status

Datum: 2026-07-02

## Ergebnis

YOLO26x ist bis zur HAILO10H-Kompilierung vorbereitet, aber noch nicht produktiv aktiv. Das System bleibt fail-closed: ohne echte `models/yolo26x_person_hailo10h_640.hef` wird keine produktive Detektion gestartet.

## Nachgewiesen

- PT vorhanden: `models/yolo26x.pt`
- PT SHA-256: `9fdd44a31c504547ffb81d2c6d9e6dac3493c8eaa8b0398d3f43bae6c7003e92`
- ONNX vorhanden: `models/yolo26x_640.onnx`
- ONNX SHA-256: `da07f5308b5392fc5a570acabd4ee2400ac57075e5255d6f2d251ddb5acb8aae`
- ONNX Checker: bestanden
- ONNX Input: `1x3x640x640`
- ONNX Output: `1x84x8400`
- Opset: `11`
- Modellsemantik: YOLO26x COCO, Filter auf COCO-Klasse `0/person`
- Produktions-HEF: fehlt noch

## OSNet

- HEF installiert: `models/osnet_x1_0_hailo10h.hef`
- Quelle: Hailo Model Zoo compiled `v5.3.0/hailo10h/osnet_x1_0.hef`
- SHA-256: `5c376b5e16cc42d8e5511aad649cc74b9503d4f44911a28ab157cbe899db1d39`
- HAILO10H-kompatibel: ja, per `hailortcli parse-hef`
- Input: `256x128x3`
- Output: `512`
- Hardwareinferenz: bestanden, 512D-Embedding, L2-Norm 1.0, gemessen ca. 6.4 ms

## Einziger externer Blocker

BOB ist `aarch64` und hat weder `hailomz` noch `hailo_compiler`. Die YOLO26x-HAILO10H-HEF muss auf einem x86_64-Hailo-DFC/Model-Zoo-Host kompiliert werden.

Compilerpaket:

- `/home/raspibob/hailo_compile_packages/yolo26x_hailo10h/`
- Archiv: `/home/raspibob/hailo_compile_packages/yolo26x_hailo10h.tar.gz`
- Archiv-SHA-256: `21e7115a7e08a3ea8fb2974d12888c7af67cab12b5f2c1601d7561e2eafc816a`

Startbefehl auf dem x86_64-Compilerhost:

```bash
cd yolo26x_hailo10h
./scripts/run_compile.sh
```
