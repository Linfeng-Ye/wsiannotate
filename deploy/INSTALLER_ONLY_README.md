# Installer-only Ubuntu package

Use this package when the Ubuntu machine already has the full
`image_subjective_test` project folder.

## Files in this package

- `install_ubuntu.sh`: one-script installer for Ubuntu.
- `requirements.txt`: Python requirements used by the installer.
- `iqa_site/settings.py` and `iqa_site/urls.py`: deployment-ready Django
  settings and URL routing for static/media files.
- `iqa/static/` and key evaluation templates: layout CSS/JS for the image
  evaluation pages.
- `deploy/cloudflared/`: Cloudflare Tunnel config template and optional credentials.
- `deploy/systemd/`: service templates.
- `scripts/configure_r2_rclone.sh`, `scripts/sync_images_to_r2.sh`, and
  `scripts/set_media_cdn.sh`: optional Cloudflare R2/CDN migration helpers.

## Typical install command

Run this from inside the extracted installer package:

```bash
chmod +x install_ubuntu.sh
./install_ubuntu.sh \
  --no-copy-project \
  --install-dir /path/to/existing/image_subjective_test \
  --service-user "$USER"
```

If this package includes the Cloudflare credential JSON, the public tunnel will
be configured automatically. Otherwise copy the JSON to `/tmp` first or pass:

```bash
./install_ubuntu.sh \
  --no-copy-project \
  --install-dir /path/to/existing/image_subjective_test \
  --tunnel-credentials /path/to/be19218c-35a5-49f2-8902-671956931026.json
```

For faster Python package downloads in China, add:

```bash
PIP_INSTALL_EXTRA="-i https://pypi.tuna.tsinghua.edu.cn/simple"
```
