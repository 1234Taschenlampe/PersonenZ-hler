from __future__ import annotations

import argparse
from pathlib import Path

from common import utc_now


def main() -> int:
    parser = argparse.ArgumentParser(description="Write PyTorch vs ONNX comparison report placeholder with required fields.")
    parser.add_argument("--output", type=Path, default=Path("reports/pytorch_vs_onnx.md"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(
            [
                "# PyTorch vs ONNX Comparison",
                "",
                f"Created: `{utc_now()}`",
                "",
                "| Image | PyTorch detections | ONNX detections | Mean confidence delta | Mean IoU | Status |",
                "|---|---:|---:|---:|---:|---|",
                "| pending | pending | pending | pending | pending | pending |",
            ]
        ),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
