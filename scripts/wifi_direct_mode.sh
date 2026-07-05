#!/usr/bin/env bash
set -euo pipefail

DIRECT_SSID="${PERSONENZAEHLER_DIRECT_SSID:-Personenzaehler-Direct}"
DIRECT_IP="${PERSONENZAEHLER_DIRECT_IP:-192.168.50.1/24}"
CONNECTION_NAME="${PERSONENZAEHLER_DIRECT_CONNECTION:-personenzaehler-direct-ap}"
ENV_FILE="${PERSONENZAEHLER_DIRECT_ENV:-$HOME/.config/personenzaehler/direct_wifi.env}"

if [[ "${1:-}" != "--yes" ]]; then
  echo "This switches wlan0 from home WiFi to a local Raspberry Pi access point."
  echo "Run again with --yes when you are ready. Existing WiFi profiles are not deleted."
  exit 2
fi

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

PASSWORD="${PERSONENZAEHLER_DIRECT_PASSWORD:-}"
if [[ ${#PASSWORD} -lt 8 ]]; then
  echo "Set PERSONENZAEHLER_DIRECT_PASSWORD with at least 8 characters in $ENV_FILE."
  echo "Example file permissions: chmod 600 $ENV_FILE"
  exit 1
fi

backup="$HOME/personenzaehler_wifi_backup_$(date +%Y%m%d_%H%M%S).txt"
nmcli -f all connection show > "$backup"
echo "Saved NetworkManager connection backup to $backup"

if nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION_NAME"; then
  nmcli connection modify "$CONNECTION_NAME" \
    connection.autoconnect no \
    802-11-wireless.mode ap \
    802-11-wireless.ssid "$DIRECT_SSID" \
    ipv4.method shared \
    ipv4.addresses "$DIRECT_IP" \
    ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD"
else
  nmcli connection add type wifi ifname wlan0 con-name "$CONNECTION_NAME" autoconnect no ssid "$DIRECT_SSID"
  nmcli connection modify "$CONNECTION_NAME" \
    802-11-wireless.mode ap \
    ipv4.method shared \
    ipv4.addresses "$DIRECT_IP" \
    ipv6.method ignore \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD"
fi

nmcli connection up "$CONNECTION_NAME"
echo "Direct WiFi active: SSID=$DIRECT_SSID Pi=http://${DIRECT_IP%/*}:8766"
