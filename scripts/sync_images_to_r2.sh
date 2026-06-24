#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_NAME="${R2_REMOTE_NAME:-wsiannotate-r2}"
BUCKET="${R2_BUCKET:-wsiannotate-images}"
SOURCE_DIR="${IMAGES_DIR:-$BASE_DIR/images}"
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

if [ ! -d "$SOURCE_DIR" ]; then
    echo "Images directory not found: $SOURCE_DIR" >&2
    exit 1
fi

"$RCLONE_BIN" sync "$SOURCE_DIR" "$REMOTE_NAME:$BUCKET/images" \
    --transfers "${RCLONE_TRANSFERS:-8}" \
    --checkers "${RCLONE_CHECKERS:-16}" \
    --s3-no-check-bucket \
    --stats 30s \
    --stats-one-line \
    --log-level NOTICE

printf '\nUploaded images to %s:%s/images\n' "$REMOTE_NAME" "$BUCKET"
