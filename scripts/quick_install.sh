#!/usr/bin/env bash
# One-command installation for Raspberry Pi OS / Debian with an existing desktop.
# Re-runs are safe: no git reset, no overwrite of local secrets or databases.
set -euo pipefail

REPO_URL="https://github.com/1234Taschenlampe/PersonenZ-hler.git"
TARGET="${PERSONENZAEHLER_INSTALL_DIR:-$HOME/.local/share/personenzaehler/app}"

say() { printf '\n[PersonenZähler] %s\n' "$*"; }
fail() { printf '[PersonenZähler] FEHLER: %s\n' "$*" >&2; exit 1; }
command -v git >/dev/null 2>&1 || {
  command -v apt-get >/dev/null 2>&1 || fail "git fehlt, apt-get ist nicht vorhanden."
  sudo apt-get update
  sudo apt-get install -y git
}

if [[ -e "$TARGET" && ! -d "$TARGET/.git" ]]; then
  fail "Ziel existiert und ist kein Git-Checkout: $TARGET. Daten bleiben unangetastet."
fi

if [[ -d "$TARGET/.git" ]]; then
  say "Vorhandene Installation prüfen: $TARGET"
  if [[ -n "$(git -C "$TARGET" status --porcelain --untracked-files=no)" ]]; then
    fail "Lokale Codeänderungen vorhanden; Update aus Sicherheitsgründen abgebrochen. Bitte vorher sichern."
  fi
  git -C "$TARGET" fetch --quiet origin main
  git -C "$TARGET" merge --ff-only origin/main ||
    fail "Kein Fast-Forward möglich; die bestehende Installation wurde nicht überschrieben."
else
  say "Projekt herunterladen ..."
  mkdir -p "$(dirname "$TARGET")"
  git clone --depth 1 --branch main "$REPO_URL" "$TARGET"
fi

# Keep user settings outside the Git working tree so future git updates work.
export PERSONENZAEHLER_USE_XDG=1
say "Systemkomponenten, virtuelle Umgebung und Desktop-Starter installieren ..."
bash "$TARGET/scripts/install_linux_app.sh"
say "Installation fertig. Öffne PersonenZähler über das Raspberry-Pi-App-Menü."
say "Konfiguration: $HOME/.config/personenzaehler/config.yaml"
say "Diagnose bei Problemen: $TARGET/scripts/check_hardware.sh"
