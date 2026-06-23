#!/usr/bin/env python3
"""Upload ADP train_2000 image files to a Cloudflare R2 bucket.

This script uses only the Python standard library. It expects an R2
S3-compatible API token in environment variables.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def signing_key(secret_key: str, date: str) -> bytes:
    key = ("AWS4" + secret_key).encode("utf-8")
    for value in (date, "auto", "s3", "aws4_request"):
        key = hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()
    return key


def sign_headers(
    *,
    method: str,
    url: str,
    body_hash: str,
    access_key: str,
    secret_key: str,
    content_type: str,
    cache_control: str,
) -> dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"

    headers = {
        "cache-control": cache_control,
        "content-type": content_type,
        "host": parsed.netloc,
        "x-amz-content-sha256": body_hash,
        "x-amz-date": amz_date,
    }
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(
        f"{name}:{headers[name]}\n" for name in sorted(headers)
    )
    canonical_request = "\n".join(
        [
            method,
            parsed.path,
            parsed.query,
            canonical_headers,
            signed_headers,
            body_hash,
        ]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(
                canonical_request.encode("utf-8")
            ).hexdigest(),
        ]
    )
    signature = hmac.new(
        signing_key(secret_key, date_stamp),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Cache-Control": cache_control,
        "Content-Type": content_type,
        "Host": parsed.netloc,
        "X-Amz-Content-Sha256": body_hash,
        "X-Amz-Date": amz_date,
    }


def iter_images(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def object_url(account_id: str, bucket: str, key: str) -> str:
    safe_bucket = urllib.parse.quote(bucket, safe="")
    safe_key = urllib.parse.quote(key, safe="/")
    return (
        f"https://{account_id}.r2.cloudflarestorage.com/"
        f"{safe_bucket}/{safe_key}"
    )


def upload_file(
    *,
    path: Path,
    key: str,
    account_id: str,
    bucket: str,
    access_key: str,
    secret_key: str,
    cache_control: str,
    timeout: int,
) -> None:
    data = path.read_bytes()
    body_hash = hashlib.sha256(data).hexdigest()
    content_type = (
        mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )
    url = object_url(account_id, bucket, key)
    headers = sign_headers(
        method="PUT",
        url=url,
        body_hash=body_hash,
        access_key=access_key,
        secret_key=secret_key,
        content_type=content_type,
        cache_control=cache_control,
    )
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status not in (200, 201):
            raise RuntimeError(
                f"Upload failed for {key}: HTTP {response.status}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        default="images/train_2000",
        help="Directory containing ADP image files.",
    )
    parser.add_argument(
        "--prefix",
        default="images/train_2000",
        help="Object key prefix to use in the bucket.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without making network calls.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-file upload timeout in seconds.",
    )
    parser.add_argument(
        "--cache-control",
        default="public, max-age=31536000, immutable",
        help="Cache-Control header for uploaded image objects.",
    )
    args = parser.parse_args()

    account_id = env_required("R2_ACCOUNT_ID")
    access_key = env_required("R2_ACCESS_KEY_ID")
    secret_key = env_required("R2_SECRET_ACCESS_KEY")
    bucket = env_required("R2_BUCKET")

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        raise SystemExit(f"Source directory not found: {source_dir}")

    files = iter_images(source_dir)
    prefix = args.prefix.strip("/")
    print(f"Found {len(files)} image files in {source_dir}")
    if args.dry_run:
        for path in files[:10]:
            key = f"{prefix}/{path.relative_to(source_dir).as_posix()}"
            print(f"DRY RUN {path} -> s3://{bucket}/{key}")
        if len(files) > 10:
            print(f"... {len(files) - 10} more files")
        return 0

    for index, path in enumerate(files, start=1):
        key = f"{prefix}/{path.relative_to(source_dir).as_posix()}"
        try:
            upload_file(
                path=path,
                key=key,
                account_id=account_id,
                bucket=bucket,
                access_key=access_key,
                secret_key=secret_key,
                cache_control=args.cache_control,
                timeout=args.timeout,
            )
        except (urllib.error.URLError, RuntimeError) as exc:
            print(f"\nERROR uploading {key}: {exc}", file=sys.stderr)
            return 1
        print(f"\rUploaded {index}/{len(files)}: {key}", end="")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
