# Deploy `wsiannotate`

Production runs on AWS + Supabase (all in Tokyo `ap-northeast-1`):

```text
AWS App Runner  ->  runs the Django app (Docker image from ECR)
Supabase Postgres ->  users, studies, stimuli, responses (session pooler)
S3 + CloudFront ->  stores and serves images globally (PriceClass_All)
```

Annotators log in with a preset username/password (Django auth, stored in
Supabase). One flow only: **Start / Resume Evaluation**, with background
sliding-window image prefetch. The old Cloudflare-tunnel / laptop deployment
and the low-latency/manual-preload modes have been removed.

## Live resources (account 143069664606, ap-northeast-1)

| Resource | Identifier |
| --- | --- |
| App Runner service | `wsiannotate` — https://draxveizjp.ap-northeast-1.awsapprunner.com |
| ECR repo | `143069664606.dkr.ecr.ap-northeast-1.amazonaws.com/wsiannotate:latest` |
| S3 bucket (private) | `wsiannotate-media-143069664606` |
| CloudFront | `E1N8NXMO6UY6XZ` — `d1v9dm2hggag7x.cloudfront.net` |
| Supabase project | `daqmygimezishrpcrxvg` (region ap-northeast-1) |
| App Runner ECR role | `AppRunnerECRAccessRole` |
| Autoscaling | `wsiannotate-min1max2` (0.5 vCPU / 1 GB, min 1 / max 2) |

## Environment variables (set on the App Runner service)

- `DJANGO_SECRET_KEY` — long random string (not the repo placeholder)
- `DATABASE_URL` — Supabase **session pooler** (port 5432), password URL-encoded:
  `postgresql://postgres.daqmygimezishrpcrxvg:<pw>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=.awsapprunner.com,wsiannotate.com,www.wsiannotate.com,localhost,127.0.0.1`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://*.awsapprunner.com,https://wsiannotate.com,https://www.wsiannotate.com`
- `DJANGO_MEDIA_URL=https://d1v9dm2hggag7x.cloudfront.net/media/`
- `DJANGO_SERVE_MEDIA_FILES=False`
- `DJANGO_USE_X_FORWARDED_HOST=True`, `DJANGO_SESSION_COOKIE_SECURE=True`, `DJANGO_CSRF_COOKIE_SECURE=True`

App Runner receives **no AWS access keys** — images are served by CloudFront
and the database is Supabase, so nothing at runtime needs the AWS API.

## Custom domain (`wsiannotate.com`, DNS on Cloudflare)

The domain is associated with the App Runner service (`--enable-www-subdomain`),
so App Runner terminates TLS with its own ACM certificate. Cloudflare only holds
the DNS records:

| Name | Type | Value | Proxy |
| --- | --- | --- | --- |
| `@` | CNAME | `draxveizjp.ap-northeast-1.awsapprunner.com` | DNS only |
| `www` | CNAME | `draxveizjp.ap-northeast-1.awsapprunner.com` | DNS only |
| 3× `_<hash>…` validation records | CNAME | `_<hash>.jkddzztszm.acm-validations.aws` | DNS only (required) |

The ACM validation CNAMEs **must** be grey-cloud; a proxied record returns
Cloudflare's own answer and certificate issuance never completes. Fetch the
current record set (they are regenerated if the domain is re-associated) with:

```bash
aws apprunner describe-custom-domains --region ap-northeast-1 \
  --service-arn arn:aws:apprunner:ap-northeast-1:143069664606:service/wsiannotate/4ea230cb207a4e3bb4f80de6e09332c1
```

Status goes `pending_certificate_dns_validation` → `active` (usually a few
minutes after the records propagate). If you later turn the orange cloud on for
`@`/`www`, set Cloudflare SSL mode to **Full (strict)** so it validates App
Runner's certificate.

## Redeploy a code change

Auto-deploy is on: pushing a new `:latest` to ECR triggers a rollout. Build a
single-platform amd64 image (the laptop is Apple Silicon; `--provenance=false`
keeps it a plain manifest App Runner can pull):

```bash
aws ecr get-login-password --region ap-northeast-1 \
  | docker login --username AWS --password-stdin \
    143069664606.dkr.ecr.ap-northeast-1.amazonaws.com
ECR=143069664606.dkr.ecr.ap-northeast-1.amazonaws.com/wsiannotate
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -t $ECR:latest --push .
```

The entrypoint serializes migrations with a PostgreSQL advisory lock, then runs
gunicorn (2 workers) on port 8080. Health check: `GET /healthz` (answered before Django's Host-header
validation by `iqa.middleware.HealthCheckMiddleware`, so App Runner's private-IP
probe passes while `ALLOWED_HOSTS` stays strict for real traffic).

## Logs

Gunicorn access logs and Django warnings stream to CloudWatch, not journald
(the systemd/laptop deployment is retired). The healthz probe runs every 3 s and
dominates the stream, so filter it out:

```bash
aws logs start-query --region ap-northeast-1 \
  --log-group-name /aws/apprunner/wsiannotate/4ea230cb207a4e3bb4f80de6e09332c1/application \
  --start-time $(( $(date +%s) - 3600 )) --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | filter @message not like "healthz" | sort @timestamp desc | limit 40'
```

`LOGGING` wires `django.security.csrf` straight to the console because Django's
own `django` logger is gated behind `require_debug_true` — without that, a CSRF
403 logs no reason at all under `DEBUG=False` and the access log shows only a
bare `POST /iqa/login/ 403`. The four reasons it prints (`CSRF cookie not set`,
`CSRF token from POST incorrect`, `Origin checking failed`, `Referer checking
failed`) each mean something different, so read it before theorising.

## Images (S3 + CloudFront)

DB image paths are `images/...`; the CDN serves them under `/media/`, so S3 keys
must be `media/images/...`. Upload with long immutable cache headers:

```bash
aws s3 sync <source>/ s3://wsiannotate-media-143069664606/media/images/<set>/ \
  --cache-control "public, max-age=31536000, immutable"
```

The bucket is private; only this CloudFront distribution can read it (OAC +
bucket policy). CloudFront has a CORS response-headers policy exposing
`Content-Length` so prefetch can inspect image sizes when needed.

Study 1 (`train_2000`) is active. Its 5,313 PNGs are stored under
`s3://wsiannotate-media-143069664606/media/images/train_2000/` and the matching
1,771-trial metadata is in Supabase. Keep those object keys stable because the
database stores their relative `images/train_2000/...` paths.

## Data / admin (from the laptop, against Supabase)

```bash
export DATABASE_URL='postgresql://postgres.daqmygimezishrpcrxvg:<url-encoded-pw>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres'
python manage.py migrate
python manage.py import_study <study.json>                 # add a study
python manage.py import_assignments <assignments.json>     # per-rater pair assignments
python scripts/bulk_load_supabase.py <fixture.json>        # fast bulk load a dump
```

`import_study` is one round-trip per row over the Tokyo pooler, so a large
study is slow and, since it is not transactional, an interruption leaves a
partial study — run it in the background (not a short-timeout foreground
call) and re-run cleanly if cut off.

### Restarting a round

Clearing responses is **not** enough: local-first mode keys its `localStorage`
on `iqa_local_<studyId>_<userId>`, and the client only re-reconciles ids the
server actually returns — so after a wipe an annotator still sees their old
progress and never re-uploads or forgets it. Give the round a new study id
instead, which orphans that local state without touching any browser:

```bash
python scripts/clone_study.py <study_id> --activate --retire-source
```

It copies the study row, every stimulus (reusing the existing `Image` rows) and
each rater's assignment, remapped to the clone's stimuli — ~19 s for 4,000 pairs
plus 20,000 assignment links — then deactivates the source and suffixes its name
with `(retired)`. Responses are deliberately not copied.

Manage studies and create annotator accounts via the Django admin
(`/admin/`, using the privately shared staff account) or the
bulk-create-users page. Staff users also get a **Progress & exports** dashboard
on the home page for per-annotator completion counts and CSV downloads.

### Per-rater assignments (2AFC)

By default every rater sees the whole study. To split a large study across a
limited pool of raters (with intentional overlap), import an assignment JSON.
Once a study has **any** assignment it becomes gated: each rater sees only
their assigned pairs, and a rater with no assignment sees nothing (so an
active, assigned study disappears for everyone not on it).

```json
{
  "study_id": 5,
  "assignments": [
    {"username": "rater1", "pairs": ["000001_x14152_y152922_0000", "..."]},
    {"username": "rater2", "pairs": ["..."]}
  ]
}
```

- `study_id` or `study_name` selects the study (2AFC only).
- Each `pairs` entry names a pair by its **stem** — the shared prefix of the
  `_a` / `_b` / `_ref` filenames (e.g. `000001_x14152_y152922_0000` for
  `images/Test/000001_x14152_y152922_0000_a.png`). The full `image_a` path and
  the bare `_a` filename are also accepted.
- Usernames must already exist (create them first); an unknown user or pair key
  aborts the whole import. Re-importing **replaces** each listed rater's set
  (idempotent); raters absent from the JSON are left untouched.
- Assignments are also editable in the Django admin (Study assignments).

## Local development

Leave `DATABASE_URL` unset to use `db.sqlite3`, and set
`DJANGO_MEDIA_URL=/media/` + `DJANGO_SERVE_MEDIA_FILES=True` to serve local
images. Run `python manage.py runserver`.

## China / global routing

CloudFront uses `PriceClass_All` for Japan and Australia edges. Mainland China
has no CloudFront edge without an ICP license, so Chinese annotators reach
Hong Kong/Tokyo edges across the GFW — variable but usually workable, and the
sliding-window prefetch absorbs the jitter. **Still validate from the actual
China hospital network** using real image URLs before the study runs.
