"""Helpers for issuing and checking one-time email codes (email_codes table).

Kept intentionally small and raw-SQL based to match the rest of the codebase.
A code is 6 digits, valid for 15 minutes, and a fresh code for the same
(email, purpose) replaces any previous one.
"""
import secrets
import hmac
import hashlib
from core.config import settings
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CODE_TTL_MINUTES = 15

def code_digest(email, code, purpose):
    return hmac.new(settings.jwt_secret_key.encode(), f"{email}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()



def generate_code() -> str:
    """A 6-digit numeric code (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


async def issue_code(db: AsyncSession, email: str, purpose: str) -> str:
    """Create and store a new code for (email, purpose), replacing any old one.

    Does not commit — the caller commits (usually alongside other work).
    """
    email = email.strip().lower()
    await db.execute(
        text("DELETE FROM email_codes WHERE LOWER(email) = :email AND purpose = :purpose"),
        {"email": email, "purpose": purpose},
    )
    code = generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
    await db.execute(
        text("""
            INSERT INTO email_codes (email, code, purpose, expires_at)
            VALUES (:email, :code, :purpose, :expires_at)
        """),
        {"email": email, "code": code_digest(email, code, purpose), "purpose": purpose, "expires_at": expires_at},
    )
    return code


async def verify_code(db: AsyncSession, email: str, code: str, purpose: str) -> bool:
    """True if the code matches and hasn't expired. Deletes it on success.

    Does not commit — the caller commits.
    """
    email = email.strip().lower()
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return False
    # DELETE RETURNING consumes a code atomically, even under concurrent requests.
    row = await db.execute(text("DELETE FROM email_codes WHERE LOWER(email) = :email AND purpose = :purpose AND (code = :digest OR code = :legacy) RETURNING expires_at"), {"email": email, "purpose": purpose, "digest": code_digest(email, code, purpose), "legacy": code})
    hit = row.fetchone()
    if not hit:
        return False
    expires = hit[0]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires >= datetime.now(timezone.utc)
