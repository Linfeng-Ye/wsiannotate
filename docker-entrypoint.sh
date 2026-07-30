#!/usr/bin/env bash
set -euo pipefail

# App Runner may start multiple instances during a rollout. Serialize Postgres
# migrations with a session-level advisory lock so only one instance executes
# migration DDL at a time; SQLite development needs no cross-process lock.
python - <<'PY'
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iqa_site.settings')

import django
from django.core.management import call_command
from django.db import connection

django.setup()

if connection.vendor == 'postgresql':
    lock_id = 8_947_231_665_020_241
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_lock(%s)', [lock_id])
    try:
        call_command('migrate', interactive=False)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [lock_id])
else:
    call_command('migrate', interactive=False)
PY

exec gunicorn iqa_site.wsgi \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
