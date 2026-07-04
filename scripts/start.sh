#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DISPLAY="${DISPLAY:-:0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec python3 -m visitor_counter.app --project-root "$PWD"
