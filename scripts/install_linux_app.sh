#!/usr/bin/env bash
# Re-entrant, ordered Raspberry Pi 5 installer. All privileged operations are
# conditional; secrets, database, user settings and nonmatching HEFs are kept.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SECRETS_DIR="$CONFIG_HOME/personenzaehler"
SECRETS_FILE="$SECRETS_DIR/api.env"
CONFIG_FILE="$SECRETS_DIR/config.yaml"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/personenzaehler"
APT_STAMP="$STATE_DIR/last-apt-update"
VENV="$PROJECT_DIR/.venv"
DRY_RUN=0
SKIP_MODELS=0

log() { echo "[PersonenZähler] $*"; }
warn() { echo "[PersonenZähler] WARNUNG: $*" >&2; }
fail() { echo "[PersonenZähler] FEHLER: $*" >&2; exit 1; }
usage() {
  echo "Verwendung: $0 [--dry-run] [--skip-models]"
  echo "  --dry-run      System prüfen und Plan ausgeben, nichts verändern"
  echo "  --skip-models  Nur bei gezielter Fehleranalyse: Modelldownload überspringen"
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unbekannte Option: $arg" ;;
  esac
done

[[ "$(uname -s)" == Linux ]] || fail "Nur Linux wird unterstützt."
command -v apt-get >/dev/null || fail "Benötigt Raspberry Pi OS / Debian mit apt."
command -v dpkg-query >/dev/null || fail "dpkg-query fehlt."
[[ "$EUID" -ne 0 ]] || fail "Nicht als root starten; sudo wird nur bei Bedarf benutzt."
[[ -f "$PROJECT_DIR/requirements-pi.txt" ]] || fail "requirements-pi.txt fehlt."
[[ -f "$PROJECT_DIR/scripts/download_models.py" ]] || fail "Modelldownload-Skript fehlt."
# Fixed systemd paths are not safely expressible without systemd quoting.
[[ "$PROJECT_DIR" != *$'\n'* ]] || fail "Installationspfad enthält Zeilenumbrüche."

export PERSONENZAEHLER_USE_XDG=1
os_name="unbekannt"
if [[ -r /etc/os-release ]]; then
  os_name="$(. /etc/os-release; echo "${PRETTY_NAME:-${ID:-Linux}}")"
fi
arch="$(dpkg --print-architecture)"
model="Keine Raspberry-Pi-Device-Tree-Erkennung"
if [[ -r /proc/device-tree/model ]]; then
  model="$(tr -d '\000' < /proc/device-tree/model)"
fi
pi5=0
if [[ "$model" == *"Raspberry Pi 5"* && "$arch" == arm64 ]]; then
  pi5=1
fi

log "1/7 Umgebung: $os_name | $(uname -m) / $arch | $model"
if [[ "$arch" != arm64 ]]; then
  warn "Keine ARM64-Plattform. Desktop/Entwicklung möglich, Hailo-10H-Treiber wird nicht installiert."
elif [[ "$pi5" -eq 0 ]]; then
  warn "Kein Raspberry Pi 5 erkannt. Treiberinstallation wird sicherheitshalber übersprungen."
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN: Es werden keine Pakete, Dateien oder Dienste verändert."
fi

installed_pkg() {
  [[ "$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null || true)" == "install ok installed" ]]
}
glib="libglib2.0-0"
if installed_pkg libglib2.0-0t64 || apt-cache show libglib2.0-0t64 >/dev/null 2>&1; then
  glib="libglib2.0-0t64"
fi
packages=(python3 python3-venv python3-pip python3-dev v4l-utils
  libgl1 libegl1 "$glib" libxcb-cursor0 libxkbcommon-x11-0
  wmctrl util-linux iproute2 ffmpeg)
missing=()
for pkg in "${packages[@]}"; do
  installed_pkg "$pkg" || missing+=("$pkg")
done
h10_needed=0
if [[ "$pi5" -eq 1 ]] && ! installed_pkg hailo-h10-all; then
  h10_needed=1
fi
log "2/7 Systempakete: ${#missing[@]} fehlend; Hailo-10H-Treiber: $([[ "$h10_needed" -eq 1 ]] && echo 'prüfen' || echo 'keine Installation')"
if [[ "${#missing[@]}" -gt 0 ]]; then
  log "Fehlende Pakete: ${missing[*]}"
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  command -v flock >/dev/null || fail "flock fehlt: util-linux installieren."
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  exec 9>"$STATE_DIR/installer.lock"
  flock -n 9 || fail "Ein anderer Installer läuft bereits."

  if [[ "${#missing[@]}" -gt 0 || "$h10_needed" -eq 1 ]]; then
    if [[ "$EUID" -eq 0 ]]; then
      apt_run=( )
    else
      command -v sudo >/dev/null || fail "sudo wird nur für fehlende Systempakete benötigt."
      sudo -v || fail "sudo-Berechtigung für Paketinstallation fehlt."
      apt_run=(sudo)
    fi
    now="$(date +%s)"
    last=0
    if [[ -r "$APT_STAMP" ]]; then
      last="$(cat "$APT_STAMP" || echo 0)"
      [[ "$last" =~ ^[0-9]+$ ]] || last=0
    fi
    if (( now - last > 86400 || now < last )); then
      log "Paketindex aktualisieren (höchstens einmal pro 24h) ..."
      "${apt_run[@]}" apt-get update
      printf '%s\n' "$now" > "$APT_STAMP"
    else
      log "Paketindex ausreichend aktuell; apt-get update übersprungen."
    fi
    if [[ "${#missing[@]}" -gt 0 ]]; then
      log "Installiere ausschließlich die fehlenden Systempakete ..."
      "${apt_run[@]}" apt-get install -y --no-install-recommends "${missing[@]}"
    fi
    if [[ "$h10_needed" -eq 1 ]]; then
      if apt-cache show hailo-h10-all >/dev/null 2>&1; then
        log "Installiere Hailo-10H / AI HAT+ 2 (nicht hailo-all) ..."
        if ! "${apt_run[@]}" apt-get install -y hailo-h10-all; then
          warn "hailo-h10-all fehlgeschlagen; GUI bleibt nutzbar. Paketquellen prüfen."
        else
          log "Hailo-10H-Treiber installiert. Für die Firmwareaktivierung kann ein Neustart nötig sein."
        fi
      else
        warn "hailo-h10-all ist in diesen apt-Paketquellen nicht vorhanden."
      fi
    fi
  else
    log "Systempakete vollständig: apt-get und sudo nicht benötigt."
  fi
fi

log "3/7 Python-Laufzeit und virtuelle Umgebung ..."
cd "$PROJECT_DIR"
if [[ "$DRY_RUN" -eq 0 ]]; then
  if [[ ! -e "$VENV/bin/python" ]]; then
    if [[ -d "$VENV" ]]; then
      fail "Vorhandene Python-Umgebung unvollständig: $VENV. Sie wurde nicht gelöscht."
    fi
    python3 -m venv --system-site-packages "$VENV"
  fi
  python_version="$("$VENV/bin/python" -c 'import sys; print(sys.version.split()[0])')"
  dependencies_hash="$(printf '%s\n' "$PROJECT_DIR" "$python_version" "$(sha256sum requirements-pi.txt pyproject.toml)" | sha256sum | cut -d' ' -f1)"
  marker="$VENV/.personenzaehler-runtime-sha256"
  installed_hash="$(cat "$marker" 2>/dev/null || true)"
  if [[ "$dependencies_hash" == "$installed_hash" ]] &&
     "$VENV/bin/python" -c 'import PySide6.QtWidgets, cv2, onnxruntime, yaml, cryptography' >/dev/null 2>&1; then
    log "Python-Pakete unverändert: pip-Installation übersprungen."
  else
    log "Python-Laufzeit fehlt oder Paketdefinition geändert; Pakete installieren ..."
    "$VENV/bin/python" -m pip install -r requirements-pi.txt
    "$VENV/bin/python" -c 'import PySide6.QtWidgets, cv2, onnxruntime, yaml, cryptography'
    printf '%s\n' "$dependencies_hash" > "$marker"
  fi
fi

log "4/7 Benutzerkonfiguration und Schlüssel ..."
if [[ "$DRY_RUN" -eq 0 ]]; then
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"
  if [[ -L "$SECRETS_FILE" || -L "$CONFIG_FILE" ]]; then
    fail "Symlink in der Sicherheitskonfiguration erkannt; Installation angehalten."
  fi
  if [[ ! -e "$SECRETS_FILE" ]]; then
    log "Erstelle neue API-Schlüssel (einmalig) ..."
    "$VENV/bin/python" scripts/generate_secrets.py --output "$SECRETS_FILE"
    chmod 600 "$SECRETS_FILE"
  else
    log "API-Schlüssel vorhanden: unverändert."
  fi
  if [[ ! -e "$CONFIG_FILE" ]]; then
    log "Erzeuge sichere Standardkonfiguration; erster Start öffnet weiterhin den Assistenten."
    "$VENV/bin/python" -c 'from visitor_counter.configuration import AppConfig; from visitor_counter.settings_service import SettingsService; from visitor_counter.runtime_paths import RuntimePaths; p=RuntimePaths.discover(); SettingsService(p.config_file).save(AppConfig())'
  else
    log "Kameras, Schwellwerte, Datenschutz und API-Einstellungen vorhanden: unverändert."
  fi
fi

log "5/7 Offizielle Hailo-10H-Modelle (SHA-256-Prüfung) ..."
models_ok=1
if [[ "$SKIP_MODELS" -eq 1 ]]; then
  warn "Modelldownload ausdrücklich übersprungen."
  models_ok=0
elif [[ "$DRY_RUN" -eq 0 ]]; then
  if ! "$VENV/bin/python" scripts/download_models.py --kind all; then
    models_ok=0
    warn "Mindestens ein HEF fehlt oder ist nicht kompatibel. Später über KI & Hardware erneut versuchen."
  fi
fi

log "6/7 Menüeintrag und Benutzer-Systemdienste ..."
if [[ "$DRY_RUN" -eq 0 ]]; then
  bash scripts/install_desktop_icon.sh
  bash scripts/install_autostart.sh
fi

log "7/7 Abschlussprüfung ..."
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY-RUN beendet. Keine Änderung am System vorgenommen."
  exit 0
fi
"$VENV/bin/python" scripts/download_models.py --check || models_ok=0
if command -v hailortcli >/dev/null 2>&1; then
  hailortcli fw-control identify || warn "Hailo-Hardware/Firmware noch nicht einsatzbereit (eventuell Neustart)."
else
  warn "HailoRT noch nicht installiert; automatische Zählung noch nicht abgenommen."
fi
log "Desktop: Anwendungen → Personenzaehler"
log "Konfiguration: $CONFIG_FILE"
log "Secrets: $SECRETS_FILE (bereits bestehende Schlüssel wurden beibehalten)"
log "Statusdienste: systemctl --user status personenzaehler.service personenzaehler-mobile-api.service"
if [[ "$models_ok" -eq 0 ]]; then
  warn "Einrichtung nur teilweise abgeschlossen (Modelle prüfen). Dieselbe Installation darf erneut laufen."
  exit 2
fi
log "Software und Original-HEFs eingerichtet. Jetzt Kameras über den Einrichtungsassistenten verbinden und echte Hailo-Inferenz testen."
