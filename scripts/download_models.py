#!/usr/bin/env python3
"""Install pinned official Hailo-10H YOLO26m and OSNet HEFs from Hailo.

Requires network access to Hailo's model-zoo S3 storage. Refuses checksum
mismatches and never silently replaces nonmatching local model files.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visitor_counter.model_installation import (  # noqa: E402
    ModelInstallationError,
    ModelInstallationService,
)
from visitor_counter.runtime_paths import RuntimePaths  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offizielle Hailo-10H-Modelle installieren")
    parser.add_argument(
        "--kind", choices=["detector", "reid", "all"], default="all",
        help="detector = YOLO26m, reid = OSNet x1.0",
    )
    parser.add_argument(
        "--system-layout", action="store_true",
        help="DEB-Installation: Dateien über PolicyKit in /var/lib installieren",
    )
    parser.add_argument(
        "--check", action="store_true", help="Nur vorhandene Dateien/Hashes prüfen"
    )
    args = parser.parse_args(argv)
    paths = RuntimePaths.discover(ROOT, system_layout=args.system_layout)
    installer = ModelInstallationService(paths)
    kinds = ["detector", "reid"] if args.kind == "all" else [args.kind]
    failures = 0
    for kind in kinds:
        try:
            url, checksum = installer._official_source(kind)
            target = paths.model_dir / installer.TARGETS[kind]
            print(f"[{kind}] Originalquelle: {url}", flush=True)
            if args.check:
                if (
                    target.is_file()
                    and not target.is_symlink()
                    and installer._digest(target) == checksum
                ):
                    print(f"[{kind}] SHA-256 korrekt: {target}", flush=True)
                else:
                    print(f"[{kind}] FEHLT oder SHA-256 falsch: {target}", flush=True)
                    failures += 1
                continue
            result = installer.download_official(kind)
            print(
                f"[{kind}] Heruntergeladen/überprüft: {result.path} "
                f"({result.size_bytes} Bytes; SHA-256 korrekt)",
                flush=True,
            )
            # This validates HEF metadata, NOT the ability to run inference.
            if subprocess.run(
                ["which", "hailortcli"], capture_output=True, check=False
            ).returncode == 0:
                inspected = subprocess.run(
                    ["hailortcli", "parse-hef", str(result.path)],
                    capture_output=True, text=True, check=False, timeout=30,
                )
                output = inspected.stdout + "\n" + inspected.stderr
                if inspected.returncode or "HAILO10H" not in output.upper():
                    print(
                        f"[{kind}] WARNUNG: HailoRT konnte HAILO10H-HEF "
                        "nicht bestätigen. Treiber-/Firmwareversion prüfen.",
                        file=sys.stderr,
                    )
                    failures += 1
                else:
                    print(f"[{kind}] HailoRT-Metadaten: HAILO10H", flush=True)
            else:
                print(f"[{kind}] HailoRT noch nicht vorhanden: Hardwareprüfung ausstehend")
        except (ModelInstallationError, OSError, subprocess.TimeoutExpired) as exc:
            print(f"[{kind}] FEHLER: {exc}", file=sys.stderr)
            failures += 1
    if failures:
        print(
            "Mindestens eine Modellprüfung ist offen. Keine produktive "
            "Inferenzbereitschaft bestätigt.",
            file=sys.stderr,
        )
        return 1
    print(
        "Beide Modelldateien geprüft (soweit ausgewählt). "
        "Reale Inferenz und Erkennung müssen am Raspberry Pi getestet werden."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
