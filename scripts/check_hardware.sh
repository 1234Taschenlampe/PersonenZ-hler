#!/usr/bin/env bash
set -u
echo "== System =="
uname -a
echo
echo "== Kameras =="
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices
else
  echo "v4l2-ctl nicht installiert"
fi
ls -l /dev/v4l/by-path 2>/dev/null || true
ls -l /dev/video* 2>/dev/null || true
echo
echo "== Hailo =="
if command -v hailortcli >/dev/null 2>&1; then
  hailortcli --version
  hailortcli fw-control identify
else
  echo "hailortcli nicht gefunden"
fi
echo
echo "== Temperatur =="
if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
  awk '{ printf "%.1f C\n", $1 / 1000 }' /sys/class/thermal/thermal_zone0/temp
fi
