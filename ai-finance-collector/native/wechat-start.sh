#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p ../data/wechat
if [ ! -f ../data/wechat/service.env ]; then
  .venv/bin/python -c 'import secrets; from pathlib import Path; p=Path("../data/wechat/service.env"); p.write_text("WECHAT_SECRET_KEY="+secrets.token_urlsafe(48)+"\n");p.chmod(0o600)'
fi
exec docker compose --env-file ../data/wechat/service.env -f compose.wechat.yaml up -d
