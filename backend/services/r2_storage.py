"""Optional S3-compatible object storage for report photos.

When storage is configured, report images are uploaded to the bucket and only
their public URL is persisted in `reports.image_data` (instead of a large base64
blob, which bloats the Postgres database). If storage is not configured — or an
upload fails — callers fall back to storing the original base64 data URI, so
nothing breaks before storage is set up.

The module is provider-agnostic (works with Yandex Object Storage, Selectel,
Cloudflare R2, AWS S3, …). Preferred generic env vars:
  S3_ENDPOINT_URL      full S3 endpoint, e.g. https://storage.yandexcloud.net
  S3_REGION            region, e.g. ru-central1  (default "auto")
  S3_ACCESS_KEY_ID     access key id
  S3_SECRET_ACCESS_KEY secret access key
  S3_BUCKET            bucket name, e.g. zubchek-photos
  S3_PUBLIC_BASE_URL   public base url of the bucket, e.g.
                       https://zubchek-photos.storage.yandexcloud.net

Legacy Cloudflare R2 vars are still accepted as a fallback (so the old Railway
config keeps working): R2_ACCOUNT_ID (→ endpoint), R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL.
"""
import base64
import logging
import os
import uuid

logger = logging.getLogger(__name__)

_EXT_BY_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}


def _first(*names: str) -> str:
    """Return the first non-empty env var among names (stripped), else ""."""
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return ""


def _resolve_endpoint() -> str:
    """S3 endpoint URL. Explicit S3_ENDPOINT_URL wins; else derive the
    Cloudflare R2 endpoint from R2_ACCOUNT_ID (tolerating a full URL paste)."""
    explicit = _first("S3_ENDPOINT_URL")
    if explicit:
        return explicit.rstrip("/")
    account = _first("R2_ACCOUNT_ID")
    if not account:
        return ""
    account = account.replace("https://", "").replace("http://", "")
    account = account.split(".r2.cloudflarestorage.com", 1)[0].strip("/")
    return f"https://{account}.r2.cloudflarestorage.com"


def _cfg() -> dict:
    return {
        "endpoint": _resolve_endpoint(),
        "region": _first("S3_REGION", "R2_REGION") or "auto",
        "access_key": _first("S3_ACCESS_KEY_ID", "R2_ACCESS_KEY_ID"),
        "secret_key": _first("S3_SECRET_ACCESS_KEY", "R2_SECRET_ACCESS_KEY"),
        "bucket": _first("S3_BUCKET", "R2_BUCKET"),
        "public_base": _first("S3_PUBLIC_BASE_URL", "R2_PUBLIC_BASE_URL").rstrip("/"),
    }


def r2_configured() -> bool:
    """True when object storage is fully configured (name kept for back-compat)."""
    c = _cfg()
    return all([c["endpoint"], c["access_key"], c["secret_key"], c["bucket"], c["public_base"]])


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
    """Upload a base64 data URI to object storage; return its public URL. Raises on failure."""
    import boto3
    from botocore.config import Config

    c = _cfg()
    data, content_type, ext = _parse_data_uri(data_uri)
    key = f"reports/{uuid.uuid4().hex}.{ext}"

    client = boto3.client(
        "s3",
        endpoint_url=c["endpoint"],
        aws_access_key_id=c["access_key"],
        aws_secret_access_key=c["secret_key"],
        config=Config(signature_version="s3v4"),
        region_name=c["region"],
    )
    client.put_object(Bucket=c["bucket"], Key=key, Body=data, ContentType=content_type)
    return f"{c['public_base']}/{key}"


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
