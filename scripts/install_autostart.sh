#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
unit_dir="$HOME/.config/systemd/user"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/personenzaehler"
mkdir -p "$unit_dir" "$config_dir" "$PWD/logs"
service="$unit_dir/visitor-counter.service"
secrets="$config_dir/api.env"
config_file="$config_dir/config.yaml"
changed=0
write_if_changed() {
  local target="$1"
  if [[ -f "$target" ]] && cmp -s "$target.new" "$target"; then
    rm -f "$target.new"
  else
    mv -f "$target.new" "$target"
    changed=1
    echo "Dienstkonfiguration aktualisiert: $target"
  fi
}
cat > "$service.new" <<SERVICE
[Unit]
Description=YOLO26m Dual-Camera Visitor Counter GUI
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$PWD
Environment=PYTHONPATH=$PWD/src
Environment=PERSONENZAEHLER_USE_XDG=${PERSONENZAEHLER_USE_XDG:-1}
EnvironmentFile=-$secrets
ExecStart=$PWD/.venv/bin/python -m visitor_counter.app --project-root $PWD
ExecStop=/usr/bin/touch $PWD/logs/visitor_counter.stop
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=20
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
RestrictSUIDSGID=true

[Install]
WantedBy=graphical-session.target
SERVICE
# The GUI is separate from the headless counter and mobile status API. All
# three services use the same user configuration, never the system-wide
# /etc/personenzaehler paths reserved for .deb installs.
write_if_changed "$service"
counter="$unit_dir/personenzaehler.service"
cat > "$counter.new" <<SERVICE
[Unit]
Description=PersonenZähler - headless camera inference and counting
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory=$PWD
Environment=PYTHONPATH=$PWD/src
Environment=PERSONENZAEHLER_USE_XDG=1
EnvironmentFile=-$secrets
ExecCondition=$PWD/.venv/bin/python $PWD/scripts/service_preflight.py --project-root $PWD
ExecStart=$PWD/.venv/bin/python -m visitor_counter.service --project-root $PWD
Restart=on-failure
RestartSec=10
TimeoutStopSec=25
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
RestrictSUIDSGID=true

[Install]
WantedBy=default.target
SERVICE

write_if_changed "$counter"
api="$unit_dir/personenzaehler-mobile-api.service"
cat > "$api.new" <<SERVICE
[Unit]
Description=PersonenZähler - mobile status API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$PWD
Environment=PYTHONPATH=$PWD/src
Environment=PERSONENZAEHLER_USE_XDG=1
EnvironmentFile=-$secrets
ExecStart=$PWD/.venv/bin/python $PWD/scripts/status_api.py --project-root $PWD --config $config_file
Restart=on-failure
RestartSec=8
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
RestrictSUIDSGID=true

[Install]
WantedBy=default.target
SERVICE

write_if_changed "$api"
if ! command -v systemctl >/dev/null 2>&1 ||
   ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "WARNUNG: systemd-Benutzerbus nicht erreichbar (SSH ohne User-Session?)."
  echo "Unit-Dateien liegen bereit; bei der nächsten Desktop-Anmeldung den Installer erneut ausführen."
  exit 0
fi
if [[ "$changed" -eq 1 ]]; then
  systemctl --user daemon-reload
else
  echo "Systemd-Konfiguration unverändert: daemon-reload übersprungen."
fi
for unit in visitor-counter.service personenzaehler.service personenzaehler-mobile-api.service; do
  if ! systemctl --user is-enabled --quiet "$unit"; then
    systemctl --user enable "$unit"
  fi
done
if [[ -f "$config_file" && -f "$secrets" ]]; then
  if systemctl --user is-active --quiet personenzaehler-mobile-api.service; then
    if [[ "$changed" -eq 1 || "${PERSONENZAEHLER_CODE_UPDATED:-0}" == 1 ]]; then
      systemctl --user restart personenzaehler-mobile-api.service
    fi
  else
    systemctl --user start personenzaehler-mobile-api.service
  fi
else
  echo "API erst starten, wenn Konfiguration und geheime Schlüssel vorhanden sind."
fi
# Never start an unconfigured camera pipeline from the installer.
if systemctl --user is-active --quiet personenzaehler.service; then
  if [[ "$changed" -eq 1 || "${PERSONENZAEHLER_CODE_UPDATED:-0}" == 1 ]]; then
    systemctl --user restart personenzaehler.service
  fi
fi
# Desktop session variables may be provided by the login manager on Wayland.
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR XDG_SESSION_TYPE >/dev/null 2>&1 || true
echo "Installierte Dienste:"
echo "  GUI:     visitor-counter.service"
echo "  Zählung: personenzaehler.service (über GUI starten, nach Einrichtung Autostart)"
echo "  API:     personenzaehler-mobile-api.service (lokal; extern nur mit TLS/Auth)"
