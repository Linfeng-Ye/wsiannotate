#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$BASE_DIR/.env}"
MEDIA_URL="${1:-${DJANGO_MEDIA_URL:-https://cdn.wsiannotate.com/}}"

if [ ! -f "$ENV_FILE" ]; then
    echo ".env not found: $ENV_FILE" >&2
    exit 1
fi

if ! grep -q '^DJANGO_MEDIA_URL=' "$ENV_FILE"; then
    printf '\nDJANGO_MEDIA_URL=%s\n' "$MEDIA_URL" >> "$ENV_FILE"
else
    tmp="$(mktemp)"
    awk -v media_url="$MEDIA_URL" '
        BEGIN { done = 0 }
        /^DJANGO_MEDIA_URL=/ {
            print "DJANGO_MEDIA_URL=" media_url
            done = 1
            next
        }
        { print }
        END {
            if (!done) print "DJANGO_MEDIA_URL=" media_url
        }
    ' "$ENV_FILE" > "$tmp"
    cat "$tmp" > "$ENV_FILE"
    rm -f "$tmp"
fi

printf 'Set DJANGO_MEDIA_URL=%s in %s\n' "$MEDIA_URL" "$ENV_FILE"
printf 'Restart with:\n'
printf '  sudo systemctl restart wsiannotate\n'
