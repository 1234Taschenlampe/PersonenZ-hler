#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_DIR="$HOME/.config/personenzaehler"
SECRETS_FILE="$SECRETS_DIR/api.env"

log() { printf '[Personenzaehler] %s\n' "$*"; }
fail() { printf '[Personenzaehler] FEHLER: %s\n' "$*" >&2; exit 1; }

if [[ "$(uname -s)" != "Linux" ]]; then
  fail "Dieser Installer ist fuer Linux vorgesehen."
fi

if ! command -v apt-get >/dev/null 2>&1; then
  fail "Aktuell wird Debian/Raspberry Pi OS mit apt unterstuetzt."
fi

log "Installiere Systemabhaengigkeiten ..."
sudo apt-get update
GLIB_PKG="libglib2.0-0t64"
if ! apt-cache show "$GLIB_PKG" >/dev/null 2>&1; then
  GLIB_PKG="libglib2.0-0"
fi
sudo apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  v4l-utils libgl1 "$GLIB_PKG" libxcb-cursor0 \
  wmctrl util-linux iproute2 ffmpeg dkms

# The desktop/setup/diagnostic UI must still install when the AI hardware is
# temporarily disconnected or the vendor packages are not yet configured.
if ! command -v hailortcli >/dev/null 2>&1; then
  # Hailo-10H / AI HAT+ 2 uses hailo-h10-all, NOT hailo-all (Hailo-8/8L).
  if apt-cache show hailo-h10-all >/dev/null 2>&1; then
    log "Installiere den Raspberry-Pi-Hailo-10H-Treiber (hailo-h10-all) ..."
    if sudo apt-get install -y hailo-h10-all; then
      log "Hailo-10H-Treiber installiert. Ein Neustart kann zur Aktivierung nötig sein."
    else
      log "WARNUNG: hailo-h10-all konnte nicht installiert werden. GUI/Diagnose bleiben verfügbar."
    fi
  else
    log "WARNUNG: Hailo-10H-Paket nicht im aktuellen apt-Repository; Raspberry Pi OS und Paketquellen prüfen."
  fi
fi

if command -v hailortcli >/dev/null 2>&1; then
  log "Pruefe Hailo-Geraet ..."
  hailortcli fw-control identify || log "WARNUNG: Hailo erkannt, aber noch nicht betriebsbereit."
else
  log "WARNUNG: Hailo-10H und passende Firmware später unter KI & Hardware prüfen."
fi

cd "$PROJECT_DIR"
log "Erstelle Python-Umgebung mit Zugriff auf die systemweiten Hailo-Python-Bindings ..."
if [[ ! -d .venv ]]; then
  python3 -m venv --system-site-packages .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

mkdir -p logs data models "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

if [[ ! -f "$SECRETS_FILE" ]]; then
  log "Erzeuge lokale API- und Verschluesselungsschluessel ..."
  python scripts/generate_secrets.py --output "$SECRETS_FILE"
else
  log "Vorhandene Secrets bleiben unveraendert: $SECRETS_FILE"
fi
chmod 600 "$SECRETS_FILE"

DETECTOR_MODEL="models/yolo26m_detection_hailo10h_640.hef"
REID_MODEL="models/osnet_x1_0_hailo10h.hef"
log "Lade offiziell kompilierte Hailo-10H-Modelle herunter (nur von Hailo, mit SHA-256-Prüfung) ..."
if ! python scripts/download_models.py --kind all; then
  log "WARNUNG: Mindestens ein Modell fehlt oder konnte nicht verifiziert werden."
  log "Im Menü KI & Hardware können die Originalmodelle später nachgeladen werden."
  log "Prüfe HailoRT-/Firmwareversion sowie Netzwerkverbindung."
fi

log "Installiere Desktop-Starter und Autostart ..."
PERSONENZAEHLER_USE_XDG="${PERSONENZAEHLER_USE_XDG:-1}" ./scripts/install_desktop_icon.sh
PERSONENZAEHLER_USE_XDG="${PERSONENZAEHLER_USE_XDG:-1}" ./scripts/install_autostart.sh

log "Pruefe Hardware und Installation ..."
./scripts/check_hardware.sh || true

cat <<EOF

Installation abgeschlossen.

Start:
  ./scripts/start_gui.sh

Secrets:
  $SECRETS_FILE

Wichtig fuer den eindeutigen Tageszaehler:
  - YOLO26m Detection HEF: $PROJECT_DIR/$DETECTOR_MODEL
  - OSNet ReID HEF:       $PROJECT_DIR/$REID_MODEL
  - VISITOR_COUNTER_DATA_KEY wird aus $SECRETS_FILE geladen.

Betreiberangaben können später in der Anwendung ergänzt werden; geltende Vorgaben vor dem Kameraeinsatz eigenverantwortlich prüfen.
Einrichtung und Diagnose sind auch ohne Hailo/HEFs zugänglich; reale Zählung setzt die richtigen HEFs und funktionsfähige Hardware voraus.
EOF
