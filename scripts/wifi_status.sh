#!/usr/bin/env bash
set -euo pipefail

echo "== hostname -I =="
hostname -I || true

echo "== ip addr =="
ip addr

echo "== ip route =="
ip route

echo "== wifi link =="
iwgetid || true

echo "== NetworkManager devices =="
nmcli device status || true

echo "== saved WiFi connections =="
nmcli -t -f NAME,TYPE,AUTOCONNECT connection show | awk -F: '$2 == "802-11-wireless" {print $0}' || true

echo "== status API listener =="
ss -lntp | grep ':8766' || true
