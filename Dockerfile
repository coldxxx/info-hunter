# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS web
WORKDIR /build
COPY ai-finance-radar/package.json ai-finance-radar/package-lock.json ./
RUN npm ci
COPY ai-finance-radar/ ./
RUN npm run build:container

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    RADAR_DATA_DIR=/data RADAR_BACKUP_DIR=/backups \
    RADAR_CONNECTIONS_FILE=/data/connections.local.json \
    RADAR_STATIC_DIR=/app/static RADAR_BIND_HOST=0.0.0.0 RADAR_PORT=43187
WORKDIR /app
COPY ai-finance-collector/*.py ai-finance-collector/sources.json ./
COPY --from=web /build/container-dist/ ./static/
EXPOSE 43187
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:43187/api/status',timeout=3)" || exit 1
CMD ["python", "radar.py", "serve"]
