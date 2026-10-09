#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/personenzaehler"
service="$HOME/.config/systemd/user/visitor-counter.service"
secrets="$HOME/.config/personenzaehler/api.env"
cat > "$service" <<SERVICE
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
cat > "$HOME/.config/systemd/user/personenzaehler.service" <<SERVICE
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

cat > "$HOME/.config/systemd/user/personenzaehler-mobile-api.service" <<SERVICE
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
ExecStart=$PWD/.venv/bin/python $PWD/scripts/status_api.py --project-root $PWD --config $HOME/.config/personenzaehler/config.yaml
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

systemctl --user daemon-reload
systemctl --user enable visitor-counter.service
systemctl --user enable personenzaehler.service
systemctl --user enable --now personenzaehler-mobile-api.service
# Desktop session variables may be provided by the login manager on Wayland.
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR XDG_SESSION_TYPE >/dev/null 2>&1 || true
echo "Installierte Dienste:"
echo "  GUI:     visitor-counter.service"
echo "  Zählung: personenzaehler.service (über GUI starten, nach Einrichtung Autostart)"
echo "  API:     personenzaehler-mobile-api.service (lokal; extern nur mit TLS/Auth)"
