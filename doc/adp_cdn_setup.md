# ADP CDN setup

This app can keep Django local for login, annotation, and checkpoints while
serving ADP images from a CDN.

## Cloudflare R2 bucket

Create an R2 bucket, connect a public custom domain such as:

```text
cdn.wsiannotate.com
```

Create an R2 API token with object write access to that bucket. Export these
variables on the server:

```bash
export R2_ACCOUNT_ID="your_cloudflare_account_id"
export R2_ACCESS_KEY_ID="your_r2_access_key_id"
export R2_SECRET_ACCESS_KEY="your_r2_secret_access_key"
export R2_BUCKET="your_bucket_name"
```

## Upload only ADP photos

From the project directory:

```bash
cd /home/wsi/DeployFiles/image_subjective_test
.venv/bin/python scripts/upload_adp_to_r2.py --dry-run
.venv/bin/python scripts/upload_adp_to_r2.py
```

The script uploads only image files from:

```text
images/train_2000/
```

It preserves the same object keys, for example:

```text
images/train_2000/P36.png_crop_251_0000_b.png
```

## Point Django image URLs to the CDN

Set:

```bash
export DJANGO_MEDIA_URL="https://cdn.wsiannotate.com/"
```

Then restart the app:

```bash
cd /home/wsi/DeployFiles/image_subjective_test
.venv/bin/python manage.py collectstatic --noinput
pkill -f "manage.py runserver"
.venv/bin/python manage.py runserver 0.0.0.0:8000
```

After this, stored image paths such as:

```text
images/train_2000/example.png
```

render as:

```text
https://cdn.wsiannotate.com/images/train_2000/example.png
```

## CORS

For browser preloading to work, configure the bucket/CDN to allow GET requests
from the annotation site, for example:

```text
https://wsiannotate.com
https://www.wsiannotate.com
```
