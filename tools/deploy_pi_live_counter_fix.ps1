param(
    [string]$PiHost = "192.168.179.25",
    [string]$PiUser = "raspibob",
    [string]$RemoteRepo = "/home/raspibob/PersonenZ-hler"
)

$ErrorActionPreference = "Stop"

$files = @(
    "src/visitor_counter/configuration.py",
    "src/visitor_counter/database.py",
    "src/visitor_counter/identity_manager.py",
    "src/visitor_counter/inference_pipeline.py",
    "tests/unit/test_counter.py",
    "tests/integration/test_database.py"
)

scp @files "$PiUser@$PiHost`:/tmp/"

$remoteScript = @"
set -e
cd "$RemoteRepo"
cp /tmp/configuration.py src/visitor_counter/configuration.py
cp /tmp/database.py src/visitor_counter/database.py
cp /tmp/identity_manager.py src/visitor_counter/identity_manager.py
cp /tmp/inference_pipeline.py src/visitor_counter/inference_pipeline.py
cp /tmp/test_counter.py tests/unit/test_counter.py
cp /tmp/test_database.py tests/integration/test_database.py
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_counter.py tests/unit/test_identity_manager.py tests/unit/test_configuration.py tests/integration/test_database.py -q
systemctl --user restart visitor-counter.service
sleep 15
systemctl --user is-active visitor-counter.service
pgrep -af 'python.*visitor_counter.app' || true
tail -n 260 logs/application.log | grep -E 'LIVE_GLOBAL_COUNTER|GUI_COUNTER_UPDATE|CAMERA_CAPTURE camera=camera_[12]|Hailo-Inferenz aktiv|COUNT_REJECTED' | tail -n 120 || true
"@

($remoteScript -replace "`r", "") | ssh "$PiUser@$PiHost" bash -s
