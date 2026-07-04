#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/gui_launcher.log"
LOCK_FILE="$LOG_DIR/gui_launcher.lock"
PID_FILE="$LOG_DIR/gui_launcher.pid"
mkdir -p "$LOG_DIR"

show_error() {
  local message="$1"
  printf '%s\n' "$message" | tee -a "$LOG_FILE" >&2
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title="Personenzaehler" --text="$message" >/dev/null 2>&1 || true
  elif command -v kdialog >/dev/null 2>&1; then
    kdialog --error "$message" --title "Personenzaehler" >/dev/null 2>&1 || true
  elif [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    "$PROJECT_DIR/.venv/bin/python" - "$message" >/dev/null 2>&1 <<'PY' || true
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication([])
QMessageBox.critical(None, "Personenzaehler", sys.argv[1])
PY
  fi
}

raise_existing() {
  if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -a "YOLO26x Dual-Kamera Besucherzaehler" >/dev/null 2>&1 && return 0
    wmctrl -a "Personenzähler" >/dev/null 2>&1 && return 0
  fi
  return 1
}

{
  echo "==== $(date -Is) launcher start ===="
  echo "PROJECT_DIR=$PROJECT_DIR"
} >> "$LOG_FILE"

cd "$PROJECT_DIR" || { show_error "Projektverzeichnis konnte nicht geoeffnet werden: $PROJECT_DIR"; exit 2; }

if [ ! -x "$PROJECT_DIR/.venv/bin/python" ]; then
  show_error "Python-Umgebung fehlt: $PROJECT_DIR/.venv/bin/python"
  exit 3
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  if [ -S "/run/user/$(id -u)/wayland-0" ]; then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
  elif [ -S "/tmp/.X11-unix/X0" ]; then
    export DISPLAY="${DISPLAY:-:0}"
  else
    show_error "Kein grafisches Display gefunden. Bitte aus der Raspberry-Pi-Desktopumgebung starten."
    exit 4
  fi
fi

if ! "$PROJECT_DIR/.venv/bin/python" - <<'PY' >> "$LOG_FILE" 2>&1; then
import PySide6.QtWidgets
PY
  show_error "PySide6 ist in der virtuellen Umgebung nicht importierbar."
  exit 5
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Instanz laeuft bereits." >> "$LOG_FILE"
  raise_existing || true
  exit 0
fi

if [ -s "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "PID aus $PID_FILE laeuft bereits." >> "$LOG_FILE"
  raise_existing || true
  exit 0
fi

echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT
export PYTHONPATH="$PROJECT_DIR/src:${PYTHONPATH:-}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec "$PROJECT_DIR/.venv/bin/python" -m visitor_counter.app --project-root "$PROJECT_DIR" >> "$LOG_FILE" 2>&1
