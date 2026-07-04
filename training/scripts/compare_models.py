from __future__ import annotations

import argparse
from pathlib import Path

from common import utc_now


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a comparison report skeleton for YOLO11x vs custom YOLO26x.")
    parser.add_argument("--output", type=Path, default=Path("reports/yolo11x_vs_yolo26x.md"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(
            [
                "# YOLO11x vs Custom YOLO26x Person Comparison",
                "",
                f"Created: `{utc_now()}`",
                "",
                "| Metric | YOLO11x HAILO10H | Custom YOLO26x Person HAILO10H | Winner |",
                "|---|---:|---:|---|",
                "| Precision | pending | pending | pending |",
                "| Recall | pending | pending | pending |",
                "| mAP50 | pending | pending | pending |",
                "| mAP50-95 | pending | pending | pending |",
                "| Empty-scene false positives | pending | pending | pending |",
                "| Hand obstruction false positives | pending | pending | pending |",
                "| Inference FPS | pending | pending | pending |",
                "| Total latency | pending | pending | pending |",
                "",
                "YOLO26x must not become primary until real tests show parity or improvement.",
            ]
        ),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
