#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$HOME/Desktop"
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR" "$APP_DIR"

desktop_file_content() {
  cat <<DESKTOP
[Desktop Entry]
Type=Application
Name=Personenzähler
Comment=YOLO26x Dual-Kamera Personenzähler starten
Exec=$PROJECT_DIR/scripts/start_gui.sh
Path=$PROJECT_DIR
Icon=camera-video
Terminal=false
Categories=Utility;Video;
StartupNotify=true
DESKTOP
}

desktop_file_content > "$DESKTOP_DIR/Personenzaehler.desktop"
desktop_file_content > "$APP_DIR/personenzaehler.desktop"
chmod +x "$DESKTOP_DIR/Personenzaehler.desktop" "$APP_DIR/personenzaehler.desktop"

if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/Personenzaehler.desktop" metadata::trusted true >/dev/null 2>&1 || true
fi

echo "$DESKTOP_DIR/Personenzaehler.desktop"
echo "$APP_DIR/personenzaehler.desktop"
