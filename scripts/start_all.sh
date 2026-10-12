#!/usr/bin/env bash
set -euo pipefail
systemctl --user start personenzaehler.service personenzaehler-mobile-api.service
bash "$(dirname "$0")/desktop_session.sh"
