#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$HOME/Desktop"
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR" "$APP_DIR"

desktop_file_content() {
  local exec_command="$PROJECT_DIR/scripts/start_gui.sh"
  if [[ "${PERSONENZAEHLER_USE_XDG:-}" == "1" ]]; then
    exec_command="env PERSONENZAEHLER_USE_XDG=1 $PROJECT_DIR/scripts/start_gui.sh"
  fi
  cat <<DESKTOP
[Desktop Entry]
Type=Application
Name=Personenzaehler
Comment=YOLO26m Dual-Kamera Personenzaehler starten
Exec=$exec_command
Path=$PROJECT_DIR
Icon=camera-video
Terminal=false
Categories=Utility;
StartupNotify=true
DESKTOP
}

update_desktop_file() {
  local target="$1"
  if [[ -f "$target" ]] && cmp -s "$target" <(desktop_file_content); then
    echo "Desktop-Verknüpfung unverändert: $target"
    return
  fi
  desktop_file_content > "$target"
  chmod +x "$target"
  echo "Desktop-Verknüpfung aktualisiert: $target"
}
update_desktop_file "$DESKTOP_DIR/Personenzaehler.desktop"
update_desktop_file "$APP_DIR/personenzaehler.desktop"

if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/Personenzaehler.desktop" metadata::trusted true >/dev/null 2>&1 || true
fi

echo "$DESKTOP_DIR/Personenzaehler.desktop"
echo "$APP_DIR/personenzaehler.desktop"
