"""Optional Cloudflare R2 (S3-compatible) object storage for report photos.

When the R2_* env vars are set, report images are uploaded to R2 and only their
public URL is persisted in `reports.image_data` (instead of a large base64 blob,
which bloats the Postgres/Neon database). If R2 is not configured — or an upload
fails — callers fall back to storing the original base64 data URI, so nothing
breaks before R2 is set up.

Required env vars (set in Railway):
  R2_ACCOUNT_ID        Cloudflare account id
  R2_ACCESS_KEY_ID     R2 API token access key id
  R2_SECRET_ACCESS_KEY R2 API token secret
  R2_BUCKET            bucket name, e.g. zubchek-photos
  R2_PUBLIC_BASE_URL   public base url of the bucket (r2.dev url or custom domain),
                       e.g. https://pub-xxxx.r2.dev  or  https://img.zubchek.com
"""
import base64
import logging
import os
import uuid

logger = logging.getLogger(__name__)

_REQUIRED = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE_URL")

_EXT_BY_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}


def r2_configured() -> bool:
    """True when every required R2 env var is present and non-empty."""
    return all(os.getenv(k) for k in _REQUIRED)


def _parse_data_uri(data_uri: str) -> tuple[bytes, str, str]:
    """Return (raw_bytes, content_type, file_extension) for a base64 data URI."""
    header, b64 = data_uri.split(",", 1)
    content_type = "image/jpeg"
    if header.startswith("data:") and ";" in header:
        maybe = header[5:].split(";", 1)[0].strip()
        if maybe:
            content_type = maybe
    ext = _EXT_BY_TYPE.get(content_type.lower(), "jpg")
    return base64.b64decode(b64), content_type, ext


def upload_data_uri(data_uri: str) -> str:
    """Upload a base64 data URI to R2 and return its public URL. Raises on failure."""
    import boto3
    from botocore.config import Config

    account = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET"]
    base_url = os.environ["R2_PUBLIC_BASE_URL"].rstrip("/")

    data, content_type, ext = _parse_data_uri(data_uri)
    key = f"reports/{uuid.uuid4().hex}.{ext}"

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    return f"{base_url}/{key}"


def store_image(data_uri: str) -> str:
    """Value to persist in reports.image_data.

    Returns the R2 public URL when R2 is configured and the upload succeeds;
    otherwise returns the original input unchanged (base64 data URI, or an
    already-stored URL). Never raises — falls back gracefully.
    """
    if not data_uri or not data_uri.startswith("data:"):
        return data_uri  # already a URL, or empty
    if not r2_configured():
        return data_uri
    try:
        return upload_data_uri(data_uri)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"R2 upload failed, keeping base64 in DB: {e}")
        return data_uri
