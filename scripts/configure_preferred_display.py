#!/usr/bin/env python3
"""Opt-in Wayland preferred mode persistence; preserve existing kanshi config."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def preferred_profile(outputs: list[dict], output_name: str | None = None) -> str:
    candidates = [o for o in outputs if o.get("enabled") and (not output_name or o.get("name") == output_name)]
    if len(candidates) != 1:
        raise ValueError("Choose --output when more than one enabled monitor is connected")
    output = candidates[0]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", output.get("name", "")):
        raise ValueError("Invalid monitor identifier")
    modes = [m for m in output.get("modes", []) if m.get("preferred")]
    if len(modes) != 1:
        raise ValueError("Monitor has no unique preferred mode")
    mode = modes[0]
    width, height, refresh = int(mode["width"]), int(mode["height"]), float(mode["refresh"])
    if width <= 0 or height <= 0 or not 1 <= refresh <= 1000:
        raise ValueError("Invalid monitor mode")
    return f"profile personenzaehler {{\n  output {output['name']} enable mode {width}x{height}@{refresh:.6f}Hz position 0,0 scale 1\n}}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = subprocess.run(["wlr-randr", "--json"], check=True, capture_output=True, text=True, timeout=10)
    profile = preferred_profile(json.loads(result.stdout), args.output)
    print(profile, end="")
    if args.apply:
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "kanshi" / "config"
        config.parent.mkdir(parents=True, exist_ok=True)
        with config.open("x", encoding="utf-8") as stream:
            stream.write(profile)
        print("New kanshi profile saved. Existing configurations are never overwritten; activate kanshi in the desktop session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
