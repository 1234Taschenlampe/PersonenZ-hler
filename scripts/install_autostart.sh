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
Environment=DISPLAY=:0
Environment=QT_QPA_PLATFORM=xcb
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
systemctl --user daemon-reload
systemctl --user enable visitor-counter.service
echo "Installed user autostart: $service"
