#!/usr/bin/env bash
# One-command Pi bootstrap: only update fast-forward code; re-run safely.
set -euo pipefail

REPO_URL="https://github.com/1234Taschenlampe/PersonenZ-hler.git"
TARGET="${PERSONENZAEHLER_INSTALL_DIR:-$HOME/.local/share/personenzaehler/app}"
OFFLINE=0
DRY_RUN=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1; ARGS+=("$arg") ;;
    --offline) OFFLINE=1 ;;
    --skip-models) ARGS+=("$arg") ;;
    -h|--help)
      echo "Aufruf: bash quick_install.sh [--dry-run] [--offline] [--skip-models]"
      exit 0 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 1 ;;
  esac
done
say() { echo "[PersonenZähler] $*"; }
fail() { echo "[PersonenZähler] FEHLER: $*" >&2; exit 1; }

[[ "$TARGET" != *" "* && "$TARGET" != *$'\n'* ]] ||
  fail "Installationspfad enthält Leerzeichen/Zeilenumbrüche; bitte einen einfachen Pfad verwenden."

if [[ "$DRY_RUN" -eq 1 ]]; then
  say "Trockentest: kein Git-Download und keine Systemänderung."
  if [[ -f "$TARGET/scripts/install_linux_app.sh" ]] &&
     grep -Fq "DRY_RUN=0" "$TARGET/scripts/install_linux_app.sh"; then
    bash "$TARGET/scripts/install_linux_app.sh" "${ARGS[@]}"
  elif [[ -f "$TARGET/scripts/install_linux_app.sh" ]]; then
    say "Lokaler Installer ist zu alt für einen schreibfreien Test. Keine Ausführung."
    exit 1
  else
    say "Ein Erststart würde das Repository unter $TARGET klonen."
  fi
  exit 0
fi

command -v flock >/dev/null 2>&1 || fail "flock fehlt (util-linux)."
mkdir -p "$HOME/.cache/personenzaehler"
exec 8>"$HOME/.cache/personenzaehler/quick-install.lock"
flock -n 8 || fail "Ein Schnellinstaller läuft bereits."

if ! command -v git >/dev/null 2>&1; then
  [[ "$OFFLINE" -eq 0 ]] || fail "Git fehlt; Offline-Modus nicht möglich."
  command -v apt-get >/dev/null 2>&1 || fail "Git fehlt und apt-get ist nicht vorhanden."
  sudo -v || fail "sudo-Berechtigung für einmalige Git-Installation erforderlich."
  sudo apt-get update
  sudo apt-get install -y git
fi

if [[ -e "$TARGET" && ! -d "$TARGET/.git" ]]; then
  fail "Ziel existiert, ist aber kein Git-Checkout: $TARGET. Nichts überschrieben."
fi

if [[ -d "$TARGET/.git" ]]; then
  say "Vorhandene Installation prüfen: $TARGET"
  if [[ -n "$(git -C "$TARGET" status --porcelain --untracked-files=no)" ]]; then
    fail "Lokale Codeänderungen vorhanden. Kein automatisches Überschreiben."
  fi
  old_rev="$(git -C "$TARGET" rev-parse HEAD)"
  if [[ "$OFFLINE" -eq 1 ]]; then
    say "Offline: vorhandenen Code verwenden."
  elif git -C "$TARGET" fetch --quiet origin main; then
    git -C "$TARGET" merge --ff-only origin/main ||
      fail "Kein Fast-Forward möglich; lokaler Code bleibt erhalten."
  else
    say "WARNUNG: GitHub nicht erreichbar; lokale Installation wird weiterverwendet."
  fi
  new_rev="$(git -C "$TARGET" rev-parse HEAD)"
  if [[ "$old_rev" != "$new_rev" ]]; then
    export PERSONENZAEHLER_CODE_UPDATED=1
  fi
else
  [[ "$OFFLINE" -eq 0 ]] || fail "Lokales Repository fehlt; Erstinstallation braucht Internet."
  say "Projekt aus GitHub laden ..."
  mkdir -p "$(dirname "$TARGET")"
  git clone --depth 1 --branch main "$REPO_URL" "$TARGET"
  export PERSONENZAEHLER_CODE_UPDATED=1
fi

export PERSONENZAEHLER_USE_XDG=1
say "Erkannte Umgebung einrichten (ohne bestehende Daten zu überschreiben) ..."
bash "$TARGET/scripts/install_linux_app.sh" "${ARGS[@]}"
say "Software-Installation beendet. Programm im Raspberry-Pi-App-Menü öffnen."
say "Konfiguration: ${XDG_CONFIG_HOME:-$HOME/.config}/personenzaehler/config.yaml"
say "Diagnose: $TARGET/scripts/check_hardware.sh"
