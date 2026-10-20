"""S3-compatible object storage for report photos.

When storage is configured, report images are uploaded to the bucket and only
their public URL is persisted in `reports.image_data` (instead of a large base64
blob, which bloats the Postgres database). If storage is not configured — or an
upload fails — callers fall back to storing the original base64 data URI, so
nothing breaks before storage is set up.

The module is provider-agnostic (Timeweb, Yandex Object Storage, Selectel, AWS
S3, …). Production currently runs on Timeweb S3. Env vars:
  S3_ENDPOINT_URL      full S3 endpoint, e.g. https://s3.twcstorage.ru
  S3_REGION            region, e.g. ru-1  (default "auto")
  S3_ACCESS_KEY_ID     access key id
  S3_SECRET_ACCESS_KEY secret access key
  S3_BUCKET            bucket name, e.g. zubchek-photos
  S3_PUBLIC_BASE_URL   public base url of the bucket, e.g.
                       https://s3.twcstorage.ru/zubchek-photos
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


def _env(name: str) -> str:
    """Return the env var stripped, or "" when unset/blank."""
    return (os.getenv(name) or "").strip()


def _cfg() -> dict:
    return {
        "endpoint": _env("S3_ENDPOINT_URL").rstrip("/"),
        "region": _env("S3_REGION") or "auto",
        "access_key": _env("S3_ACCESS_KEY_ID"),
        "secret_key": _env("S3_SECRET_ACCESS_KEY"),
        "bucket": _env("S3_BUCKET"),
        "public_base": _env("S3_PUBLIC_BASE_URL").rstrip("/"),
    }


def storage_configured() -> bool:
    """True when object storage is fully configured."""
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

    Returns the bucket's public URL when storage is configured and the upload
    succeeds; otherwise returns the original input unchanged (base64 data URI,
    or an already-stored URL). Never raises — falls back gracefully.
    """
    if not data_uri or not data_uri.startswith("data:"):
        return data_uri  # already a URL, or empty
    if not storage_configured():
        return data_uri
    try:
        return upload_data_uri(data_uri)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"S3 upload failed, keeping base64 in DB: {e}")
        return data_uri
