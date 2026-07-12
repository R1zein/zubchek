"""Helpers for issuing and checking one-time email codes (email_codes table).

Kept intentionally small and raw-SQL based to match the rest of the codebase.
A code is 6 digits, valid for 15 minutes, and a fresh code for the same
(email, purpose) replaces any previous one.
"""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CODE_TTL_MINUTES = 15


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
        {"email": email, "code": code, "purpose": purpose, "expires_at": expires_at},
    )
    return code


async def verify_code(db: AsyncSession, email: str, code: str, purpose: str) -> bool:
    """True if the code matches and hasn't expired. Deletes it on success.

    Does not commit — the caller commits.
    """
    email = email.strip().lower()
    code = (code or "").strip()
    row = await db.execute(
        text("""
            SELECT id, expires_at FROM email_codes
            WHERE LOWER(email) = :email AND purpose = :purpose AND code = :code
            ORDER BY id DESC LIMIT 1
        """),
        {"email": email, "purpose": purpose, "code": code},
    )
    hit = row.fetchone()
    if not hit:
        return False

    expires_at = hit[1]
    now = datetime.now(timezone.utc)
    # expires_at may be naive depending on the driver; normalize to aware UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        await db.execute(text("DELETE FROM email_codes WHERE id = :id"), {"id": hit[0]})
        return False

    await db.execute(text("DELETE FROM email_codes WHERE id = :id"), {"id": hit[0]})
    return True
