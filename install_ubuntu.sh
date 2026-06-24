#!/usr/bin/env bash
set -euo pipefail

APP_LABEL="WSI Annotate"
DEFAULT_INSTALL_DIR="/opt/wsiannotate/image_subjective_test"
DEFAULT_TUNNEL_ID="be19218c-35a5-49f2-8902-671956931026"

INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
SERVICE_GROUP="${SERVICE_GROUP:-}"
DOMAIN="${DOMAIN:-wsiannotate.com}"
WWW_DOMAIN="${WWW_DOMAIN:-www.wsiannotate.com}"
TUNNEL_ID="${CLOUDFLARE_TUNNEL_ID:-$DEFAULT_TUNNEL_ID}"
TUNNEL_CREDENTIALS="${CLOUDFLARE_TUNNEL_CREDENTIALS:-}"
WORKERS="${WEB_CONCURRENCY:-2}"
CONFIGURE_CLOUDFLARED=1
COPY_PROJECT=1

usage() {
    cat <<'EOF'
Install WSI Annotate on Ubuntu.

Usage:
  ./install_ubuntu.sh [options]

Options:
  --install-dir PATH          Install path. Default: /opt/wsiannotate/image_subjective_test
  --service-user USER         Linux user that runs Gunicorn. Default: current sudo user
  --service-group GROUP       Linux group for installed files. Default: user's primary group
  --domain DOMAIN             Main hostname. Default: wsiannotate.com
  --www-domain DOMAIN         WWW hostname. Default: www.wsiannotate.com
  --tunnel-id ID              Cloudflare Tunnel ID.
  --tunnel-credentials PATH   Path to the Cloudflare Tunnel credential JSON.
  --skip-cloudflared          Install only the Django/Gunicorn service.
  --no-copy-project           Use the existing project at --install-dir.
  --workers N                 Gunicorn worker count. Default: 2
  -h, --help                  Show this help.

Optional environment:
  PIP_INSTALL_EXTRA="-i https://pypi.tuna.tsinghua.edu.cn/simple"
EOF
}

log() {
    printf '\n[%s] %s\n' "$APP_LABEL" "$*"
}

die() {
    printf '\n[%s] ERROR: %s\n' "$APP_LABEL" "$*" >&2
    exit 1
}

as_root() {
    if [ "${EUID}" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

shell_quote() {
    printf '%q' "$1"
}

run_as_service_user() {
    local command="$1"
    if [ "$SERVICE_USER" = "root" ]; then
        bash -lc "$command"
    else
        sudo -u "$SERVICE_USER" bash -lc "$command"
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --install-dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --service-user)
            SERVICE_USER="$2"
            shift 2
            ;;
        --service-group)
            SERVICE_GROUP="$2"
            shift 2
            ;;
        --domain)
            DOMAIN="$2"
            shift 2
            ;;
        --www-domain)
            WWW_DOMAIN="$2"
            shift 2
            ;;
        --tunnel-id)
            TUNNEL_ID="$2"
            shift 2
            ;;
        --tunnel-credentials)
            TUNNEL_CREDENTIALS="$2"
            shift 2
            ;;
        --skip-cloudflared)
            CONFIGURE_CLOUDFLARED=0
            shift
            ;;
        --no-copy-project)
            COPY_PROJECT=0
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

command -v sudo >/dev/null 2>&1 || [ "${EUID}" -eq 0 ] || die "sudo is required."
id "$SERVICE_USER" >/dev/null 2>&1 || die "Linux user '$SERVICE_USER' does not exist."

if [ -z "$SERVICE_GROUP" ]; then
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"
SOURCE_REAL="$(realpath "$SOURCE_DIR")"
TARGET_REAL="$(realpath -m "$INSTALL_DIR")"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
INSTALL_PARENT="$(dirname "$INSTALL_DIR")"

log "Installing system packages"
as_root apt-get update
as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    curl \
    gpg \
    rsync \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    build-essential

log "Copying project to $INSTALL_DIR"
as_root mkdir -p "$INSTALL_PARENT"
if [ "$COPY_PROJECT" -eq 1 ] && [ -d "$INSTALL_DIR" ]; then
    if [ -f "$INSTALL_DIR/db.sqlite3" ]; then
        as_root cp -a "$INSTALL_DIR/db.sqlite3" \
            "$INSTALL_DIR/db.sqlite3.backup.$TIMESTAMP"
    fi
    if [ -f "$INSTALL_DIR/.env" ]; then
        as_root cp -a "$INSTALL_DIR/.env" \
            "$INSTALL_DIR/.env.backup.$TIMESTAMP"
    fi
fi

if [ "$COPY_PROJECT" -eq 1 ] && [ "$SOURCE_REAL" != "$TARGET_REAL" ]; then
    as_root mkdir -p "$INSTALL_DIR"
    as_root rsync -a \
        --exclude='.venv/' \
        --exclude='staticfiles/' \
        --exclude='dist/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.DS_Store' \
        --exclude='.env' \
        --exclude='local_passwd.txt' \
        "$SOURCE_DIR"/ "$INSTALL_DIR"/
fi

if [ "$COPY_PROJECT" -eq 0 ] && [ ! -f "$INSTALL_DIR/manage.py" ]; then
    die "Existing project not found at $INSTALL_DIR. Pass --install-dir PATH."
fi

if [ "$COPY_PROJECT" -eq 0 ]; then
    for relative_path in \
        requirements.txt \
        iqa_site/settings.py \
        iqa_site/urls.py \
        iqa/templates/base.html \
        iqa/templates/iqa/mos_evaluation.html \
        iqa/templates/iqa/pair_evaluation.html \
        scripts/run_production.sh \
        scripts/configure_r2_rclone.sh \
        scripts/sync_images_to_r2.sh \
        scripts/set_media_cdn.sh \
        deploy/cloudflared/config.yml.example \
        deploy/systemd/wsiannotate.service \
        deploy/systemd/cloudflared-wsiannotate.service
    do
        if [ -f "$SOURCE_DIR/$relative_path" ]; then
            as_root mkdir -p "$INSTALL_DIR/$(dirname "$relative_path")"
            if [ -f "$INSTALL_DIR/$relative_path" ]; then
                as_root cp -a "$INSTALL_DIR/$relative_path" \
                    "$INSTALL_DIR/$relative_path.backup.$TIMESTAMP"
            fi
            as_root cp "$SOURCE_DIR/$relative_path" \
                "$INSTALL_DIR/$relative_path"
        fi
    done
    for relative_dir in iqa/static; do
        if [ -d "$SOURCE_DIR/$relative_dir" ]; then
            if [ -d "$INSTALL_DIR/$relative_dir" ]; then
                as_root cp -a "$INSTALL_DIR/$relative_dir" \
                    "$INSTALL_DIR/$relative_dir.backup.$TIMESTAMP"
            fi
            as_root mkdir -p "$INSTALL_DIR/$(dirname "$relative_dir")"
            as_root rsync -a --delete \
                "$SOURCE_DIR/$relative_dir"/ \
                "$INSTALL_DIR/$relative_dir"/
        fi
    done
    as_root chmod +x "$INSTALL_DIR"/scripts/*.sh 2>/dev/null || true
fi

as_root mkdir -p "$INSTALL_DIR/media"
if [ -e "$INSTALL_DIR/media/images" ] && [ ! -L "$INSTALL_DIR/media/images" ]; then
    as_root mv "$INSTALL_DIR/media/images" \
        "$INSTALL_DIR/media/images.backup.$TIMESTAMP"
fi
as_root ln -sfn ../images "$INSTALL_DIR/media/images"
as_root chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"

log "Writing environment file"
SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(64))
PY
)"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    as_root tee "$INSTALL_DIR/.env" >/dev/null <<EOF
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_ALLOWED_HOSTS=$DOMAIN,$WWW_DOMAIN,localhost,127.0.0.1,[::1]
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN,https://$WWW_DOMAIN
DJANGO_USE_X_FORWARDED_HOST=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_MEDIA_ROOT=$INSTALL_DIR/media
DJANGO_SERVE_MEDIA_FILES=True
EOF
fi
as_root chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/.env"
as_root chmod 600 "$INSTALL_DIR/.env"

log "Creating Python virtual environment"
Q_INSTALL_DIR="$(shell_quote "$INSTALL_DIR")"
PIP_EXTRA="${PIP_INSTALL_EXTRA:-}"
run_as_service_user "cd $Q_INSTALL_DIR && python3 -m venv .venv"
run_as_service_user "cd $Q_INSTALL_DIR && .venv/bin/python -m pip install --upgrade pip setuptools wheel"
run_as_service_user "cd $Q_INSTALL_DIR && .venv/bin/python -m pip install $PIP_EXTRA -r requirements.txt"

log "Checking Django and collecting static files"
run_as_service_user "cd $Q_INSTALL_DIR && set -a && source .env && set +a && .venv/bin/python manage.py check"
run_as_service_user "cd $Q_INSTALL_DIR && set -a && source .env && set +a && .venv/bin/python manage.py collectstatic --noinput"

log "Installing Gunicorn systemd service"
as_root tee /etc/systemd/system/wsiannotate.service >/dev/null <<EOF
[Unit]
Description=WSI Annotate Django application
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/gunicorn iqa_site.wsgi:application --bind 127.0.0.1:8000 --workers $WORKERS --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

as_root systemctl daemon-reload
as_root systemctl enable --now wsiannotate

find_tunnel_credentials() {
    if [ -n "$TUNNEL_CREDENTIALS" ] && [ -f "$TUNNEL_CREDENTIALS" ]; then
        printf '%s\n' "$TUNNEL_CREDENTIALS"
        return 0
    fi

    local candidate
    for candidate in \
        "$INSTALL_DIR/deploy/cloudflared/credentials/$TUNNEL_ID.json" \
        "$INSTALL_DIR/deploy/cloudflared/$TUNNEL_ID.json" \
        "$INSTALL_DIR/$TUNNEL_ID.json" \
        "/tmp/$TUNNEL_ID.json"
    do
        if [ -f "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}

if [ "$CONFIGURE_CLOUDFLARED" -eq 1 ]; then
    log "Installing cloudflared"
    if ! command -v cloudflared >/dev/null 2>&1; then
        as_root mkdir -p --mode=0755 /usr/share/keyrings
        curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg |
            as_root tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
        echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" |
            as_root tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
        as_root apt-get update
        as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflared
    fi

    if CREDENTIAL_PATH="$(find_tunnel_credentials)"; then
        log "Configuring Cloudflare Tunnel"
        as_root mkdir -p /etc/cloudflared
        as_root cp "$CREDENTIAL_PATH" "/etc/cloudflared/$TUNNEL_ID.json"
        as_root chmod 600 "/etc/cloudflared/$TUNNEL_ID.json"
        as_root tee /etc/cloudflared/config.yml >/dev/null <<EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json
protocol: http2

ingress:
  - hostname: $DOMAIN
    service: http://127.0.0.1:8000
  - hostname: $WWW_DOMAIN
    service: http://127.0.0.1:8000
  - service: http_status:404
EOF
        as_root tee /etc/systemd/system/cloudflared-wsiannotate.service >/dev/null <<EOF
[Unit]
Description=Cloudflare Tunnel for WSI Annotate
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared --config /etc/cloudflared/config.yml tunnel run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        as_root systemctl daemon-reload
        as_root systemctl enable --now cloudflared-wsiannotate
    else
        log "Cloudflare credential JSON was not found; Django was installed, but the public tunnel was not started."
        log "Put $TUNNEL_ID.json in /tmp or rerun with --tunnel-credentials /path/to/$TUNNEL_ID.json."
    fi
fi

log "Installation complete"
printf '\nLocal check:\n'
printf '  curl -I http://127.0.0.1:8000/iqa/\n'
printf '\nService checks:\n'
printf '  systemctl status wsiannotate --no-pager\n'
if [ "$CONFIGURE_CLOUDFLARED" -eq 1 ]; then
    printf '  systemctl status cloudflared-wsiannotate --no-pager\n'
fi
printf '\nPublic URL:\n'
printf '  https://%s/\n' "$DOMAIN"
