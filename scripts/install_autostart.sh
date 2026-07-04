#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p "$HOME/.config/systemd/user"
service="$HOME/.config/systemd/user/visitor-counter.service"
cat > "$service" <<SERVICE
[Unit]
Description=YOLO26x Dual-Camera Visitor Counter GUI
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$PWD
Environment=PYTHONPATH=$PWD/src
Environment=DISPLAY=:0
Environment=QT_QPA_PLATFORM=xcb
ExecStart=$PWD/.venv/bin/python -m visitor_counter.app --project-root $PWD
ExecStop=/usr/bin/touch $PWD/logs/visitor_counter.stop
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=graphical-session.target
SERVICE
systemctl --user daemon-reload
systemctl --user enable visitor-counter.service
echo "Installed user autostart: $service"
