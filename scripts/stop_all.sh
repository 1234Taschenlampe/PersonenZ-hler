#!/usr/bin/env bash
set -euo pipefail
systemctl --user stop visitor-counter.service personenzaehler-mobile-api.service personenzaehler.service
