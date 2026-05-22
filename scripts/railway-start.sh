#!/bin/sh
set -eu

PORT="${PORT:-8000}"

if [ -n "${RAILWAY_VOLUME_MOUNT_PATH:-}" ]; then
  mkdir -p "${RAILWAY_VOLUME_MOUNT_PATH}"
fi

alembic upgrade head

exec uvicorn fixlog.main:app --host 0.0.0.0 --port "${PORT}"
