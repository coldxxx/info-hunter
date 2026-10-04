#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || { echo 'MLX requires Apple Silicon macOS'; exit 1; }
command -v uv >/dev/null || { echo 'Install uv before running this setup'; exit 1; }
export UV_PYTHON_INSTALL_DIR="$(pwd)/.python"
export UV_CACHE_DIR="${TMPDIR:-/tmp/}signal-radar-uv-cache"
export RADAR_NATIVE_DATA="$(pwd)/../data/native"
export PLAYWRIGHT_BROWSERS_PATH="$RADAR_NATIVE_DATA/browsers"
uv python install 3.12
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements.lock
.venv/bin/python -m playwright install chromium
.venv/bin/python - <<'PY'
from model_config import model_path
print('Whisper model ready (managed by LM Studio):', model_path())
PY
echo 'Dependencies ready. Run .venv/bin/python install-launch-agent.py to enable login startup.'
