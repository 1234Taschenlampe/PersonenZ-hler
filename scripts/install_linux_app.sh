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
sudo apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  v4l-utils libgl1 libglib2.0-0 libxcb-cursor0 \
  wmctrl util-linux

if ! command -v hailortcli >/dev/null 2>&1; then
  log "HailoRT wurde nicht gefunden. Versuche auf Raspberry Pi OS das offizielle hailo-all Paket zu installieren ..."
  if sudo apt-get install -y hailo-all; then
    log "hailo-all installiert."
  else
    fail "HailoRT konnte nicht automatisch installiert werden. Richte zuerst das offizielle Hailo/Raspberry-Pi-Paketrepository ein und starte den Installer erneut."
  fi
fi

log "Pruefe Hailo-Geraet ..."
if ! hailortcli fw-control identify; then
  fail "HailoRT ist installiert, aber der Hailo-Beschleuniger wurde nicht erfolgreich identifiziert."
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
if [[ ! -s "$DETECTOR_MODEL" ]]; then
  log "Detektionsmodell fehlt: $DETECTOR_MODEL"
  log "Lege das fuer Hailo-10H kompilierte YOLO26m-HEF dort ab; die App verweigert sonst produktive Detektion."
fi
if [[ ! -s "$REID_MODEL" ]]; then
  log "Re-ID-Modell fehlt: $REID_MODEL"
  log "Fuer den eindeutigen Tageszaehler wird das OSNet-Hailo-10H-HEF benoetigt."
fi

log "Installiere Desktop-Starter und Autostart ..."
./scripts/install_desktop_icon.sh
./scripts/install_autostart.sh

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

Vor dem ersten Livebetrieb muessen die Betreiber-/Datenschutzfelder in config/config.yaml ausgefuellt werden.
EOF
