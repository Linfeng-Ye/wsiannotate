# Deployment plan: App Runner + Supabase Postgres + S3/CloudFront

Implements GitHub issue #1 plus decisions made 2026-07-08:

- **Database + auth:** Supabase Postgres (Tokyo). Login stays Django's built-in
  username/password auth with pre-created accounts (`bulk_create_users` flow) —
  user records simply live in the Supabase database. Supabase Auth (GoTrue) is
  **not** used.
- **Images:** S3 (ap-northeast-1) served through CloudFront with
  **PriceClass_All** (annotators are in China, Japan, Australia — global).
- **App:** existing Django app on AWS App Runner (ap-northeast-1), Docker image
  via ECR.
- **UX:** one Start/Resume flow with sliding-window prefetch; remove the
  low-latency/local mode and the manual full-preload mode (see issue #1).

Secrets live in the local `.env` (gitignored). Never commit them; never bake
them into the Docker image.

---

## Phase 1 — Code changes

### 1.1 Database settings (Supabase Postgres)

- Add to `requirements.txt`: `psycopg[binary]>=3.1`, `dj-database-url`.
- In `iqa_site/settings.py`, replace the hardcoded SQLite `DATABASES` with:
  - If env `DATABASE_URL` is set → `dj_database_url.parse(DATABASE_URL, conn_max_age=60, ssl_require=True)`.
  - Else fall back to the existing SQLite config (local dev keeps working).
- **Connection string rules (important):**
  - App Runner egress is IPv4-only and Supabase's direct DB host is IPv6-only
    on the free plan → must use the **Supavisor session pooler**:
    `postgresql://postgres.<project-ref>:<password>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres`
    (session mode, port **5432**, username `postgres.<project-ref>`).
  - Do NOT use the transaction pooler (port 6543) — it breaks Django features
    (server-side cursors, prepared statements).
  - The password contains special characters (e.g. `$`) → URL-encode it in
    `DATABASE_URL`.
  - Verify the Supabase project region is `ap-northeast-1`; if it is not,
    recreate the project in Tokyo before doing anything else (it is brand new,
    nothing to lose).

### 1.2 Remove low-latency/local mode and manual preload (issue #1)

Delete, per issue #1 acceptance criteria:

- URLs in `iqa/urls.py`: `local_assignment`, `local_annotation`,
  `preload_manifest`, `preload_service_worker`.
- Views in `iqa/views.py`: `local_assignment`, `local_annotation`,
  `preload_manifest`, `preload_service_worker`, and the `_local_*` /
  `_assignment_hash` helpers (roughly lines 365–520 and 610–662). Keep
  `_ordered_stimuli_for_preload` — rename and reuse it for the prefetch
  endpoint (1.3).
- Static: `iqa/static/iqa/js/preload.js` and any service-worker registration.
- Templates: preload / low-latency buttons and copy in `iqa/templates/iqa/home.html`.

Keep exactly one annotator path: **Start / Resume Evaluation**.

### 1.3 Sliding-window prefetch (issue #1)

- **Deterministic per-user order.** In `iqa/samplers.py`, `SAMPLER_RANDOM`
  currently uses `order_by('?')` — non-deterministic, so "next" cannot be
  predicted for prefetch. Change it to a per-`(user, study)` seeded shuffle
  (hash of user id + study id, like the old `_local_seed`), then "next" = first
  unanswered stimulus in that fixed order. `sequential` is already
  deterministic; `least_evaluated` stays best-effort (prediction may
  occasionally miss — acceptable because prefetch is an optimization only).
- **New endpoint** `GET /study/<id>/prefetch/?current=<stimulus_id>` (login
  required): returns JSON `{"images": [absolute CDN URLs...]}` for the next
  ~8 unanswered stimuli in the user's order (dedup URLs, include references).
  Cheap metadata only.
- **New `iqa/static/iqa/js/prefetch.js`**, included by both evaluation
  templates: on page load, fetch the manifest, then warm the browser HTTP
  cache with `new Image().src = url`, max 2–3 concurrent. Window: next 8,
  hard cap 24 images per page so all shared-reference 2AFC assets fit. Previous images are already in browser
  cache (the user just saw them), so no explicit previous-window handling.
  Failures must be silent/non-blocking — the real `<img>` still loads from
  CloudFront normally.
- **Basic metrics:** on prefetch error, `navigator.sendBeacon()` to a tiny
  `POST /prefetch-report/` view that writes to Python logging (visible in App
  Runner logs). No DB writes.
- Immediate per-answer saves and Previous+resubmit overwrite already work
  (`evaluation_submit` uses `update_or_create` with
  `unique_together ['stimulus','user']`) — do not change; add/keep a test.

### 1.4 Media URLs → CloudFront

No storage backend change needed. `Image.fname.url` is `MEDIA_URL + path` and
views use `request.build_absolute_uri(...)`, which passes absolute URLs
through unchanged. So:

- Set env `DJANGO_MEDIA_URL=https://<cloudfront-domain>/media/` in App Runner.
- Images are uploaded to S3 out-of-band (Phase 2), keyed to match:
  s3 key `media/images/<file>` ⇔ DB `fname='images/<file>'`.
- Keep `DJANGO_SERVE_MEDIA_FILES=False` in production.
- Admin-uploaded images won't persist on App Runner's ephemeral disk — that's
  fine; the workflow is `aws s3 sync` + `import_study`. Document this in
  DEPLOY.md.

### 1.5 Container + health check

- Add `/healthz` view (no auth, no DB query, returns 200 "ok") + URL.
- `Dockerfile`: `python:3.12-slim`; install `requirements.txt`; copy app;
  `collectstatic --noinput` at build (with a dummy `DJANGO_SECRET_KEY`);
  non-root user; expose 8080.
- `docker-entrypoint.sh`: `python manage.py migrate --noinput` then
  `gunicorn iqa_site.wsgi --bind 0.0.0.0:8080 --workers 2 --timeout 60`.
  (Single-instance service → migrate-on-boot is safe at this scale.)
- Settings: append `.awsapprunner.com` support — `DJANGO_ALLOWED_HOSTS` and
  `DJANGO_CSRF_TRUSTED_ORIGINS` come from env, so this is config, not code.
- Update `.env.example` with the new vars (`DATABASE_URL`, CDN media URL);
  update `DEPLOY.md` (the Cloudflare-tunnel instructions are obsolete).

---

## Phase 2 — AWS + Supabase provisioning (runbook)

All AWS resources in **ap-northeast-1** unless noted.

### 2.1 IAM hygiene (do first)

- The existing `AKIA…` access key should belong to an IAM user scoped to only:
  S3 read/write on the media bucket + ECR push. If it's a broad/root key,
  replace it. It also appeared in a chat screenshot — **rotate it**.
- App Runner must NOT receive AWS keys: runtime needs none (images are served
  by CloudFront, DB is Supabase). If any AWS API access is ever needed at
  runtime, use the App Runner instance role, not keys.
- Generate a real `DJANGO_SECRET_KEY`
  (`django.core.management.utils.get_random_secret_key()`); the current .env
  value is a placeholder.

### 2.2 S3

- Bucket `wsiannotate-media` (or similar), **Block Public Access ON**,
  private; access only via CloudFront OAC.
- Upload:
  `aws s3 sync media/ s3://wsiannotate-media/media/ --cache-control "public, max-age=31536000, immutable"`
  (images are content-addressed by study design and never change).

### 2.3 CloudFront

- Origin: the S3 bucket with **Origin Access Control (OAC)**; add the
  generated bucket policy.
- **Price class: PriceClass_All** — required for Sydney/Melbourne edges
  (PriceClass_200 excludes Australia; PriceClass_100 would be wrong for
  everyone). Cost difference at 6 annotators is negligible.
- Enable **HTTP/3** (helps on lossy China paths) and HTTP/2.
- Cache policy: `CachingOptimized`. Viewer protocol: redirect-to-HTTPS.
- **Response headers policy (custom):** CORS with
  `Access-Control-Allow-Origin` = the App Runner domain (and custom domain if
  added), methods `GET, HEAD`, and `Access-Control-Expose-Headers:
  Content-Length` — issue #1 wants prefetch able to inspect sizes later.
- China reality check: CloudFront has no mainland edges without an ICP
  license; Chinese annotators hit HK/Tokyo edges across the GFW. Workable but
  variable — this is exactly what the prefetch window absorbs. **The
  must-do validation is loading real image URLs from the actual China
  hospital network** (issue #1 acceptance criterion).

### 2.4 Supabase

- Confirm/ create project in **ap-northeast-1 (Tokyo)**.
- Get the **session pooler** connection string (Dashboard → Connect →
  Session mode, port 5432); URL-encode the password; this is `DATABASE_URL`.
- From the laptop, with `DATABASE_URL` exported: `python manage.py migrate`,
  `createsuperuser`, `import_study` for the real studies, then create the 6
  annotator accounts via the existing bulk-create-users page (or a management
  command). Distribute the preset username/password pairs privately.

### 2.5 ECR + App Runner

- ECR repo `wsiannotate`; build/push the image (buildx `--platform
  linux/amd64` — the laptop is Apple Silicon).
- App Runner service, ap-northeast-1, from ECR with auto-deploy:
  - **0.5 vCPU / 1 GB**, autoscaling min 1 / max 2 (min 1 avoids cold starts
    during annotation sessions). The app only serves metadata — images go via
    CloudFront — so this is ample for 6 annotators. Expect roughly
    US$10–20/month (vCPU is billed only while handling requests); Supabase
    free tier, S3/CloudFront ≈ pennies at this scale.
  - Health check: HTTP `/healthz`.
  - Env vars: `DJANGO_SECRET_KEY`, `DATABASE_URL`, `DJANGO_DEBUG=False`,
    `DJANGO_ALLOWED_HOSTS=<service>.ap-northeast-1.awsapprunner.com,wsiannotate.com,www.wsiannotate.com`,
    `DJANGO_CSRF_TRUSTED_ORIGINS=https://<service>....awsapprunner.com,https://wsiannotate.com`,
    `DJANGO_MEDIA_URL=https://<cloudfront-domain>/media/`,
    `DJANGO_SERVE_MEDIA_FILES=False`, cookie-secure flags True.
- Optional (nice-to-have): custom domains — `wsiannotate.com` → App Runner
  (Custom domains + Cloudflare DNS records), `cdn.wsiannotate.com` →
  CloudFront alternate domain (needs an ACM cert in **us-east-1**). The stack
  works fine on the default AWS domains; do this last, and if Cloudflare
  proxying (orange cloud) is on for these records, turn it off (DNS-only) to
  avoid double-CDN weirdness.

---

## Phase 3 — Verification (acceptance)

1. Local: `manage.py check` + test run against Supabase `DATABASE_URL`.
2. Deployed smoke test: login as a test annotator → Start Evaluation →
   answer several trials → Previous → change answer → confirm the DB row is
   updated, not duplicated.
3. DevTools network tab: images load from the CloudFront domain with
   `x-cache: Hit from cloudfront` on second load; prefetch requests for the
   next window fire after page load; blocking a prefetch URL does not break
   the evaluation page.
4. No `local/`, `preload` routes remain (404) and no such buttons in the UI.
5. App Runner logs show prefetch-report entries when failures are simulated.
6. Real-network test: each annotator (China hospital network especially,
   plus Japan and Australia) loads a trial page and reports timing; check
   CloudFront cache-hit metrics afterwards.
7. Export CSV still works from the researcher account.

## Explicitly out of scope

- DynamoDB (rejected: app is relational, Django ORM/admin/auth need SQL).
- Supabase Auth / GoTrue (rejected: email-based; preset username/password is
  Django auth, stored in Supabase Postgres).
- Tiled WSI delivery, multi-GB images (future work per issue #1).
