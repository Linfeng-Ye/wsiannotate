# Deploy `image_subjective_test`

This project is a Django app. The simplest way to expose it from a home
computer is Cloudflare Tunnel:

- public users visit `https://wsiannotate.com/iqa/`
- Cloudflare forwards traffic through `cloudflared`
- `cloudflared` forwards to Django on `127.0.0.1:8000`

This avoids router port forwarding and works even when your home network does
not have a public IPv4 address.

## 1. Run Django locally

```bash
cd "/Users/eric/Desktop/AI/老叶paper/image_subjective_test"
source .venv/bin/activate
python manage.py check
python manage.py collectstatic --noinput
python manage.py runserver 127.0.0.1:8000
```

Open:

```text
http://127.0.0.1:8000/iqa/
```

## 2. Production-like environment variables

Create a real `.env` from `.env.example` and replace the secret key:

```bash
cp .env.example .env
python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

For the current simple setup, you can keep `DJANGO_SERVE_MEDIA_FILES=True`.
For a larger public deployment, put media/static files behind a real web server
such as Nginx instead of Django's development server.

## 3. Cloudflare Tunnel on macOS

Current tunnel:

```text
name: wsiannotate
id: be19218c-35a5-49f2-8902-671956931026
config: /Users/eric/.cloudflared/config.yml
```

Install and log in:

```bash
brew install cloudflared
cloudflared tunnel login
```

Create a tunnel:

```bash
cloudflared tunnel create wsiannotate
cloudflared tunnel route dns wsiannotate wsiannotate.com
cloudflared tunnel route dns wsiannotate www.wsiannotate.com
```

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: wsiannotate
credentials-file: /Users/eric/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: wsiannotate.com
    service: http://127.0.0.1:8000
  - hostname: www.wsiannotate.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Run it in the foreground:

```bash
cloudflared tunnel run wsiannotate
```

Then test:

```text
https://wsiannotate.com/iqa/
```

On this Mac, `cloudflared` is installed at:

```bash
/Users/eric/.local/bin/cloudflared
```

The local Django service can be started with:

```bash
cd "/Users/eric/Desktop/AI/老叶paper/image_subjective_test"
./scripts/run_production.sh
```

The public tunnel can be started with:

```bash
/Users/eric/.local/bin/cloudflared tunnel run wsiannotate
```

## 4. Keep services running

For long-term use, run both Django and `cloudflared` as background services.
On macOS, `cloudflared service install` can install the tunnel service.
For Django, use a process manager such as `launchd`, `supervisord`, or run it
inside a terminal multiplexer while testing.

## 5. Ubuntu migration notes

On Ubuntu, the same architecture works. The easiest migration is to reuse the
existing Cloudflare tunnel and copy its credential JSON to the Ubuntu host.

1. Copy this project directory to the Ubuntu machine.
2. Install Python, create a virtual environment, and install requirements.
3. Copy `.env`, `db.sqlite3`, `images/`, and `media/images` symlink.
4. Install `cloudflared`.
5. Reuse the same Cloudflare tunnel or create a new one.
6. Run Django with a production server such as Gunicorn behind Nginx, or keep
   the same simple `runserver` pattern only for a low-risk temporary setup.

Suggested Ubuntu command shape:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt gunicorn
.venv/bin/python manage.py check
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/gunicorn iqa_site.wsgi:application --bind 127.0.0.1:8000
```

For a real public deployment, use systemd units for both Gunicorn and
`cloudflared` so they start after reboot.

### Ubuntu systemd setup

Assume the Ubuntu project path is:

```text
/opt/wsiannotate/image_subjective_test
```

Copy the project from the Mac:

```bash
rsync -av --progress \
  "/Users/eric/Desktop/AI/老叶paper/image_subjective_test/" \
  eric@UBUNTU_IP:/opt/wsiannotate/image_subjective_test/
```

On Ubuntu:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip rsync curl gpg
cd /opt/wsiannotate/image_subjective_test
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
ln -sfn ../images media/images
set -a; source .env; set +a
.venv/bin/python manage.py check
.venv/bin/python manage.py collectstatic --noinput
```

Install `cloudflared` with Cloudflare's package repository:

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg |
  sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" |
  sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update
sudo apt install -y cloudflared
```

Copy the tunnel credential from the Mac to Ubuntu:

```bash
sudo mkdir -p /etc/cloudflared
sudo cp deploy/cloudflared/config.yml.example /etc/cloudflared/config.yml
sudo cp /path/to/be19218c-35a5-49f2-8902-671956931026.json /etc/cloudflared/
sudo chmod 600 /etc/cloudflared/*.json
```

Install systemd services:

```bash
sudo cp deploy/systemd/wsiannotate.service /etc/systemd/system/
sudo cp deploy/systemd/cloudflared-wsiannotate.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wsiannotate
sudo systemctl enable --now cloudflared-wsiannotate
```

Check status:

```bash
systemctl status wsiannotate --no-pager
systemctl status cloudflared-wsiannotate --no-pager
curl -I http://127.0.0.1:8000/iqa/
curl -I https://wsiannotate.com/iqa/
```

## 6. Installer-only package

If the Ubuntu machine already has the full project folder, build only the
installer package on the Mac:

```bash
cd "/Users/eric/Desktop/AI/老叶paper/image_subjective_test"
./scripts/package_ubuntu.sh --installer-only --include-cloudflare-credentials
```

The generated package is tiny and does not include `images/`, `db.sqlite3`, or
the source tree. It does include the Cloudflare tunnel credential JSON when
`--include-cloudflare-credentials` is used, so keep it private.

On Ubuntu:

```bash
tar -xzf wsiannotate-ubuntu-*-installer-only-with-cloudflare-secret.tar.gz
cd wsiannotate-ubuntu-*-installer-only-with-cloudflare-secret
chmod +x install_ubuntu.sh
./install_ubuntu.sh \
  --no-copy-project \
  --install-dir /path/to/existing/image_subjective_test \
  --service-user "$USER"
```

If Python package downloads are slow:

```bash
PIP_INSTALL_EXTRA="-i https://pypi.tuna.tsinghua.edu.cn/simple" \
./install_ubuntu.sh \
  --no-copy-project \
  --install-dir /path/to/existing/image_subjective_test \
  --service-user "$USER"
```
