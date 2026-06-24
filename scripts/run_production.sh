#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

exec .venv/bin/gunicorn iqa_site.wsgi:application \
    --bind "${BIND_ADDRESS:-127.0.0.1:8000}" \
    --workers "${WEB_CONCURRENCY:-2}"
