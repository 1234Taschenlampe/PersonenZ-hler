#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PERSONENZAEHLER_USE_XDG=1
systemctl --user show personenzaehler.service personenzaehler-mobile-api.service visitor-counter.service -p Id -p ActiveState -p MainPID -p NRestarts
"$root/.venv/bin/python" "$root/scripts/runtime_acceptance.py" --project-root "$root" --seconds 0
