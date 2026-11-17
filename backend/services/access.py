"""Signed sessions and report permissions shared by every entry point."""
import hashlib
import hmac
import secrets
from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth import AccessTokenError, create_access_token, decode_access_token
from core.database import get_db
from schemas.auth import UserResponse

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'

def verify_password(password: str, encoded: str) -> bool:
    try:
        kind, iterations, salt, expected = encoded.split('$')
        if kind != 'pbkdf2_sha256' or int(iterations) != 600000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False

def session_token(user_id: str) -> str:
    return create_access_token({'sub': str(user_id), 'purpose': 'session'}, expires_minutes=1440)

def report_token(report_id: int) -> str:
    return create_access_token({'sub': str(report_id), 'purpose': 'report_share', 'jti': secrets.token_urlsafe(24)}, expires_minutes=7 * 1440)

def valid_report_token(token: str | None, report_id: int) -> bool:
    if not token:
        return False
    try:
        claims = decode_access_token(token)
        return claims.get('purpose') == 'report_share' and claims.get('sub') == str(report_id)
    except AccessTokenError:
        return False

async def optional_user(authorization: str | None = Header(None), db: AsyncSession = Depends(get_db)) -> UserResponse | None:
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(' ', 1)
        if scheme.lower() != 'bearer':
            raise ValueError()
        claims = decode_access_token(token)
        if claims.get('purpose') != 'session' or not claims.get('sub'):
            raise ValueError()
    except (ValueError, AccessTokenError):
        raise HTTPException(401, 'Сессия истекла. Войдите снова.')
    row = (await db.execute(text('SELECT user_id, role, full_name, email FROM users_profiles WHERE user_id = :uid'), {'uid': claims['sub']})).fetchone()
    if not row:
        raise HTTPException(401, 'Сессия недействительна. Войдите снова.')
    return UserResponse(id=row[0], role=row[1], name=row[2], email=row[3] or '')

async def require_user(user: UserResponse | None = Depends(optional_user)) -> UserResponse:
    if user is None:
        raise HTTPException(401, 'Войдите, чтобы открыть отчёт')
    return user

async def require_report_access(db: AsyncSession, report_id: int, user: UserResponse | None, share_token: str | None = None) -> str | None:
    row = (await db.execute(text('SELECT user_id FROM reports WHERE id = :id'), {'id': report_id})).fetchone()
    if not row:
        raise HTTPException(404, 'Отчёт недоступен. Войдите в свой аккаунт или получите защищённую ссылку.')
    owner = row[0]
    if valid_report_token(share_token, report_id):
        return owner
    if user and owner == str(user.id):
        return owner
    if user and user.role == 'doctor' and owner:
        linked = (await db.execute(text("SELECT 1 FROM doctor_patients WHERE user_id = :doctor AND patient_id = :patient AND status = 'active'"), {'doctor': str(user.id), 'patient': owner})).fetchone()
        if linked:
            return owner
    raise HTTPException(404, 'Отчёт недоступен. Войдите в свой аккаунт или получите защищённую ссылку.')

async def migrate_passwords(db: AsyncSession) -> None:
    """Move legacy doctor passwords out of phone on startup, before serving."""
    rows = (await db.execute(text("SELECT user_id, phone FROM users_profiles WHERE role = 'doctor' AND password_hash IS NULL"))).fetchall()
    for uid, legacy in rows:
        if legacy:
            await db.execute(text('UPDATE users_profiles SET password_hash = :hashed, phone = NULL WHERE user_id = :uid AND password_hash IS NULL'), {'uid': uid, 'hashed': hash_password(legacy)})
    await db.commit()
