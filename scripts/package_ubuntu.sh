#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$BASE_DIR/dist"
INCLUDE_CF_CREDENTIALS=0
INSTALLER_ONLY=0
TUNNEL_ID="${CLOUDFLARE_TUNNEL_ID:-be19218c-35a5-49f2-8902-671956931026}"

usage() {
    cat <<'EOF'
Build an Ubuntu install tarball.

Usage:
  scripts/package_ubuntu.sh [options]

Options:
  --include-cloudflare-credentials
      Include ~/.cloudflared/<tunnel-id>.json so Ubuntu can start the public
      tunnel during one-script installation. Keep that tarball private.

  --installer-only
      Package only the installer, deployment templates, and requirements.
      Use this when the Ubuntu machine already has the project files.

  --tunnel-id ID
      Cloudflare Tunnel ID. Defaults to the current wsiannotate tunnel.

  --out-dir PATH
      Output directory. Default: ./dist
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --include-cloudflare-credentials)
            INCLUDE_CF_CREDENTIALS=1
            shift
            ;;
        --installer-only)
            INSTALLER_ONLY=1
            shift
            ;;
        --tunnel-id)
            TUNNEL_ID="$2"
            shift 2
            ;;
        --out-dir)
            OUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

command -v rsync >/dev/null 2>&1 || {
    echo "rsync is required." >&2
    exit 1
}

mkdir -p "$OUT_DIR"
STAGE_PARENT="$(mktemp -d)"
PACKAGE_NAME="wsiannotate-ubuntu-$(date +%Y%m%d-%H%M%S)"
if [ "$INSTALLER_ONLY" -eq 1 ]; then
    PACKAGE_NAME="$PACKAGE_NAME-installer-only"
fi
if [ "$INCLUDE_CF_CREDENTIALS" -eq 1 ]; then
    PACKAGE_NAME="$PACKAGE_NAME-with-cloudflare-secret"
fi
STAGE_DIR="$STAGE_PARENT/$PACKAGE_NAME"

cleanup() {
    rm -rf "$STAGE_PARENT"
}
trap cleanup EXIT

mkdir -p "$STAGE_DIR"
if [ "$INSTALLER_ONLY" -eq 1 ]; then
    mkdir -p "$STAGE_DIR/scripts" "$STAGE_DIR/deploy" "$STAGE_DIR/iqa_site" "$STAGE_DIR/iqa"
    cp "$BASE_DIR/install_ubuntu.sh" "$STAGE_DIR/install_ubuntu.sh"
    cp "$BASE_DIR/requirements.txt" "$STAGE_DIR/requirements.txt"
    cp "$BASE_DIR/deploy/INSTALLER_ONLY_README.md" "$STAGE_DIR/README.md"
    cp "$BASE_DIR/iqa_site/settings.py" "$STAGE_DIR/iqa_site/settings.py"
    cp "$BASE_DIR/iqa_site/urls.py" "$STAGE_DIR/iqa_site/urls.py"
    mkdir -p "$STAGE_DIR/iqa/templates"
    cp -R "$BASE_DIR/iqa/templates/base.html" "$STAGE_DIR/iqa/templates/base.html"
    mkdir -p "$STAGE_DIR/iqa/templates/iqa"
    cp "$BASE_DIR/iqa/templates/iqa/mos_evaluation.html" "$STAGE_DIR/iqa/templates/iqa/mos_evaluation.html"
    cp "$BASE_DIR/iqa/templates/iqa/pair_evaluation.html" "$STAGE_DIR/iqa/templates/iqa/pair_evaluation.html"
    cp -R "$BASE_DIR/iqa/static" "$STAGE_DIR/iqa/static"
    cp "$BASE_DIR/scripts/run_production.sh" "$STAGE_DIR/scripts/run_production.sh"
    cp "$BASE_DIR/scripts/configure_r2_rclone.sh" "$STAGE_DIR/scripts/configure_r2_rclone.sh"
    cp "$BASE_DIR/scripts/sync_images_to_r2.sh" "$STAGE_DIR/scripts/sync_images_to_r2.sh"
    cp "$BASE_DIR/scripts/set_media_cdn.sh" "$STAGE_DIR/scripts/set_media_cdn.sh"
    cp -R "$BASE_DIR/deploy/cloudflared" "$STAGE_DIR/deploy/cloudflared"
    cp -R "$BASE_DIR/deploy/systemd" "$STAGE_DIR/deploy/systemd"
else
    rsync -a "$BASE_DIR"/ "$STAGE_DIR"/ \
        --exclude='.venv/' \
        --exclude='staticfiles/' \
        --exclude='dist/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.DS_Store' \
        --exclude='.env' \
        --exclude='local_passwd.txt' \
        --exclude='media/images'
fi

chmod +x "$STAGE_DIR/install_ubuntu.sh"
if [ -f "$STAGE_DIR/scripts/run_production.sh" ]; then
    chmod +x "$STAGE_DIR"/scripts/*.sh
fi

if [ "$INCLUDE_CF_CREDENTIALS" -eq 1 ]; then
    CREDENTIAL="$HOME/.cloudflared/$TUNNEL_ID.json"
    if [ ! -f "$CREDENTIAL" ]; then
        echo "Cloudflare credential not found: $CREDENTIAL" >&2
        exit 1
    fi
    mkdir -p "$STAGE_DIR/deploy/cloudflared/credentials"
    cp "$CREDENTIAL" "$STAGE_DIR/deploy/cloudflared/credentials/$TUNNEL_ID.json"
    chmod 600 "$STAGE_DIR/deploy/cloudflared/credentials/$TUNNEL_ID.json"
fi

TARBALL="$OUT_DIR/$PACKAGE_NAME.tar.gz"
COPYFILE_DISABLE=1 tar -C "$STAGE_PARENT" -czf "$TARBALL" "$PACKAGE_NAME"

echo "$TARBALL"
