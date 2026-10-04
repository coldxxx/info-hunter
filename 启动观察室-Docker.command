#!/bin/zsh
set -eu
cd "${0:A:h}"
if ! docker info >/dev/null 2>&1; then
  print '请先启动 Docker Desktop，待它就绪后再次双击。'
  read '?按回车关闭…'
  exit 1
fi
docker compose up -d --build
print '观察室已启动，请访问 http://localhost:43187/ （自定义端口见RADAR_PORT）。'
print '关闭此窗口不会停止容器；停止请运行 docker compose stop。'
read '?按回车关闭…'
