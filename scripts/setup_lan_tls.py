#!/usr/bin/env python3
"""Create private TLS files only; never change API bindings, secrets or services."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visitor_counter.tls_setup import create_lan_tls, repair_ca_usage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--hostname", required=True)
    create.add_argument("--address", action="append", default=[])
    repair = commands.add_parser("repair-ca")
    repair.add_argument("--certificate", type=Path, required=True)
    repair.add_argument("--private-key", type=Path, required=True)
    repair.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "create":
        create_lan_tls(args.output, args.hostname, args.address)
    else:
        repair_ca_usage(args.certificate, args.private_key, args.output)
    print("TLS assets created privately. Import CA trust and configure TLS explicitly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
