#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_NAME="${R2_REMOTE_NAME:-wsiannotate-r2}"
BUCKET="${R2_BUCKET:-wsiannotate-images}"
SOURCE_DIR="${IMAGES_DIR:-$BASE_DIR/images}"

if ! command -v rclone >/dev/null 2>&1; then
    echo "rclone is required. Install it first: sudo apt install -y rclone" >&2
    exit 1
fi

if [ ! -d "$SOURCE_DIR" ]; then
    echo "Images directory not found: $SOURCE_DIR" >&2
    exit 1
fi

rclone mkdir "$REMOTE_NAME:$BUCKET"
rclone sync "$SOURCE_DIR" "$REMOTE_NAME:$BUCKET/images" \
    --progress \
    --transfers "${RCLONE_TRANSFERS:-8}" \
    --checkers "${RCLONE_CHECKERS:-16}" \
    --s3-no-check-bucket

printf '\nUploaded images to %s:%s/images\n' "$REMOTE_NAME" "$BUCKET"
