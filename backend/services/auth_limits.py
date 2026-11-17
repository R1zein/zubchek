"""Database-backed rate limits shared across workers and process restarts."""
import hashlib
import time
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from core.database import get_db

async def consume(db, scope: str, identity: str, limit: int, seconds: int):
    now = int(time.time())
    key = scope + ':' + hashlib.sha256(identity.encode()).hexdigest() + ':' + str(now // seconds)
    row = (await db.execute(text('INSERT INTO auth_limits (key, hits, expires) VALUES (:key, 1, :expires) ON CONFLICT (key) DO UPDATE SET hits = auth_limits.hits + 1 RETURNING hits'), {'key': key, 'expires': now + seconds})).fetchone()
    await db.execute(text('DELETE FROM auth_limits WHERE expires < :now'), {'now': now})
    await db.commit()
    if row[0] > limit:
        raise HTTPException(429, 'Слишком много попыток. Повторите позже.', headers={'Retry-After': str(seconds)})

async def limit_auth(request: Request, db=Depends(get_db)):
    body = await request.json()
    email = str(body.get('email', '')).strip().lower() if isinstance(body, dict) else ''
    path = request.url.path
    if path.endswith(('request-code', 'register')):
        await consume(db, 'send-code', email, 1, 60)
    await consume(db, path, email, 10, 900)
