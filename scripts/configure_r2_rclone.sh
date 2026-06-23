#!/usr/bin/env bash
set -euo pipefail

REMOTE_NAME="${R2_REMOTE_NAME:-wsiannotate-r2}"
ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:-}"
SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:-}"
REGION="${R2_REGION:-auto}"
RCLONE_BIN="${RCLONE_BIN:-}"

if [ -z "$RCLONE_BIN" ]; then
    if [ -x "$HOME/bin/rclone" ]; then
        RCLONE_BIN="$HOME/bin/rclone"
    else
        RCLONE_BIN="$(command -v rclone || true)"
    fi
fi

if [ -z "$RCLONE_BIN" ]; then
    echo "rclone is required. Install a recent version first." >&2
    exit 1
fi

if [ -z "$ACCOUNT_ID" ]; then
    read -r -p "Cloudflare Account ID: " ACCOUNT_ID
fi
if [ -z "$ACCESS_KEY_ID" ]; then
    read -r -p "R2 Access Key ID: " ACCESS_KEY_ID
fi
if [ -z "$SECRET_ACCESS_KEY" ]; then
    read -r -s -p "R2 Secret Access Key: " SECRET_ACCESS_KEY
    printf '\n'
fi

mkdir -p "$HOME/.config/rclone"
"$RCLONE_BIN" config create "$REMOTE_NAME" s3 \
    provider Cloudflare \
    access_key_id "$ACCESS_KEY_ID" \
    secret_access_key "$SECRET_ACCESS_KEY" \
    endpoint "https://${ACCOUNT_ID}.r2.cloudflarestorage.com" \
    region "$REGION" >/dev/null

printf '\nConfigured rclone remote: %s\n' "$REMOTE_NAME"
printf 'Test with:\n'
printf '  rclone ls %s:<bucket-name> --s3-no-check-bucket\n' "$REMOTE_NAME"
