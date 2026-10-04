#!/bin/zsh
set -eu
RADAR_COLLECTOR_DIR="${0:A:h}"
RADAR_WEB_DIR="$RADAR_COLLECTOR_DIR/../ai-finance-radar"
cd "$RADAR_COLLECTOR_DIR"
python3 radar.py serve &
RADAR_API_PID=$!
trap 'kill "$RADAR_API_PID" 2>/dev/null || true' EXIT INT TERM
cd "$RADAR_WEB_DIR"
print '打开浏览器访问 http://127.0.0.1:43187/；关闭此窗口将停止服务。'
npm run dev
