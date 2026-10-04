#!/bin/sh
set -e

# 컨테이너 시작 시 DB 마이그레이션 적용 (RUN_MIGRATIONS=false로 끌 수 있음)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] alembic upgrade head"
    alembic upgrade head
fi

exec "$@"
