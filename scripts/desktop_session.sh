#!/usr/bin/env bash
# Run by the desktop's XDG autostart, including Labwc without an active target.
set -euo pipefail
if [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_TTY:-}" ]]; then
  echo "Desktop session environment must come from the local desktop."
  exit 1
fi
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  socket="$WAYLAND_DISPLAY"
  [[ "$socket" == /* ]] || socket="$runtime/$socket"
  [[ -S "$socket" ]] || { echo "Wayland desktop socket unavailable."; exit 1; }
  export XDG_RUNTIME_DIR="$runtime"
elif [[ -z "${DISPLAY:-}" ]]; then
  echo "No desktop display in this login session."
  exit 1
fi
variables=()
for name in DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR XDG_SESSION_TYPE QT_QPA_PLATFORM; do
  [[ -n "${!name:-}" ]] && variables+=("$name")
done
systemctl --user import-environment "${variables[@]}"
systemctl --user start visitor-counter.service
