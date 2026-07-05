#!/usr/bin/env bash
set -euo pipefail

DIRECT_CONNECTION="${PERSONENZAEHLER_DIRECT_CONNECTION:-personenzaehler-direct-ap}"
HOME_CONNECTION="${1:-${PERSONENZAEHLER_HOME_CONNECTION:-Meilo}}"

if nmcli -t -f NAME connection show | grep -Fxq "$DIRECT_CONNECTION"; then
  nmcli connection down "$DIRECT_CONNECTION" || true
fi

if ! nmcli -t -f NAME connection show | grep -Fxq "$HOME_CONNECTION"; then
  echo "Saved home WiFi profile not found: $HOME_CONNECTION"
  echo "Known WiFi profiles:"
  nmcli -t -f NAME,TYPE connection show | awk -F: '$2 == "802-11-wireless" {print " - " $1}'
  exit 1
fi

nmcli connection up "$HOME_CONNECTION"
echo "Home WiFi active: $HOME_CONNECTION"
