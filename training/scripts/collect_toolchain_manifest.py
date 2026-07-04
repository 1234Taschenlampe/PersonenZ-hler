from __future__ import annotations

import platform
from pathlib import Path

from common import run_command, utc_now


def main() -> int:
    report = {
        "created_at": utc_now(),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "commands": {
            "uname": run_command(["uname", "-a"]),
            "nvidia_smi": run_command(["nvidia-smi"]),
            "nvcc": run_command(["nvcc", "--version"]),
            "hailortcli": run_command(["hailortcli", "--version"]),
            "hailo": run_command(["hailo", "--version"]),
            "hailomz": run_command(["hailomz", "--version"]),
            "pip_freeze": run_command(["python3", "-m", "pip", "freeze"]),
        },
    }
    lines = ["# YOLO26x Person Toolchain Manifest", "", f"Generated: `{report['created_at']}`", ""]
    lines += [f"- Host: `{report['host']}`", f"- Platform: `{report['platform']}`", f"- Python: `{report['python']}`", ""]
    for name, result in report["commands"].items():
        lines += [f"## {name}", "", "```text", (result.get("stdout") or result.get("stderr") or result.get("error") or "").strip(), "```", ""]
    Path("docs/model_toolchain_manifest.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
