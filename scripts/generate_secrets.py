from __future__ import annotations

import argparse
from pathlib import Path
import secrets

from cryptography.fernet import Fernet


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a private systemd EnvironmentFile for the visitor counter.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Replace an existing secrets file intentionally.")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing secrets file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.parent.chmod(0o700)
    except OSError:
        pass
    values = {
        "VISITOR_COUNTER_VIEWER_TOKEN": secrets.token_urlsafe(32),
        "VISITOR_COUNTER_OPERATOR_TOKEN": secrets.token_urlsafe(32),
        "VISITOR_COUNTER_ADMIN_TOKEN": secrets.token_urlsafe(32),
        "VISITOR_COUNTER_DATA_KEY": Fernet.generate_key().decode("ascii"),
    }
    output.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="ascii")
    try:
        output.chmod(0o600)
    except OSError:
        pass
    print(f"Secrets written with private permissions: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
