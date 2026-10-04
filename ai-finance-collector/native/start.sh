#!/bin/sh
set -eu
cd "$(dirname "$0")"
export RADAR_NATIVE_DATA="${RADAR_NATIVE_DATA:-$(pwd)/../data/native}"
export PLAYWRIGHT_BROWSERS_PATH="$RADAR_NATIVE_DATA/browsers"
export HF_HOME="$RADAR_NATIVE_DATA/models"
export HF_HUB_OFFLINE=1
[ ! -f env.local ] || . ./env.local
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec .venv/bin/python -m uvicorn service:app --host 127.0.0.1 --port 43202 --no-access-log
