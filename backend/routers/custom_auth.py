import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.email_codes import issue_code, verify_code
from services.email_service import send_code_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/custom-auth", tags=["custom-auth"])

CLINIC_PASSWORD = "logtest121"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class DoctorLoginRequest(BaseModel):
    role: str = "doctor"
    email: str
    password: str


class DoctorRegisterRequest(BaseModel):
    role: str = "doctor"
    full_name: str
    email: str
    password: str
    clinic_password: Optional[str] = None


class VerifyEmailRequest(BaseModel):
    email: str
    code: str


class PatientRequestCodeRequest(BaseModel):
    email: str


class PatientVerifyCodeRequest(BaseModel):
    email: str
    code: str


class AuthResponse(BaseModel):
    """Unified response. When ``needs_verification`` is true the client must
    collect an emailed code (no session yet); otherwise session fields are set."""
    success: bool
    needs_verification: bool = False
    user_id: Optional[str] = None
    role: Optional[str] = None
    full_name: Optional[str] = None
    birth_date: Optional[str] = None
    email: Optional[str] = None
    message: str = ""


# ---------------------------------------------------------------------------
# Doctor registration + email verification (#3)
# ---------------------------------------------------------------------------
@router.post("/register", response_model=AuthResponse)
async def register_doctor(data: DoctorRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a doctor. Creates an unverified profile and emails a one-time
    code; the account is usable only after /verify-email."""
    full_name = (data.full_name or "").strip()
    email = (data.email or "").strip().lower()
    password = (data.password or "").strip()

    if not full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Введите корректную почту")
    if not password:
        raise HTTPException(status_code=400, detail="Пароль обязателен")
    if data.clinic_password != CLINIC_PASSWORD:
        raise HTTPException(status_code=403, detail="Неверный специальный пароль")

    # Does a doctor with this email already exist?
    existing = await db.execute(
        text("SELECT user_id, email_verified FROM users_profiles WHERE role = 'doctor' AND LOWER(TRIM(email)) = :email"),
        {"email": email},
    )
    row = existing.fetchone()
    if row and row[1]:
        raise HTTPException(status_code=409, detail="Врач с такой почтой уже зарегистрирован")

    if row:
        # Unverified attempt exists — update its details and re-send a new code.
        user_id = row[0]
        await db.execute(
            text("UPDATE users_profiles SET full_name = :full_name, phone = :password WHERE user_id = :user_id"),
            {"full_name": full_name, "password": password, "user_id": user_id},
        )
    else:
        user_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO users_profiles (user_id, role, full_name, email, phone, email_verified)
                VALUES (:user_id, 'doctor', :full_name, :email, :password, FALSE)
            """),
            {"user_id": user_id, "full_name": full_name, "email": email, "password": password},
        )

    code = await issue_code(db, email, "doctor_verify")
    await db.commit()
    await asyncio.to_thread(send_code_email, email, code, "doctor_verify")

    return AuthResponse(
        success=True,
        needs_verification=True,
        email=email,
        message="Код подтверждения отправлен на почту",
    )


@router.post("/verify-email", response_model=AuthResponse)
async def verify_doctor_email(data: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Confirm a doctor's email with the code they received, then log them in."""
    email = (data.email or "").strip().lower()

    ok = await verify_code(db, email, data.code, "doctor_verify")
    if not ok:
        await db.commit()
        raise HTTPException(status_code=400, detail="Неверный или просроченный код")

    result = await db.execute(
        text("SELECT user_id, full_name FROM users_profiles WHERE role = 'doctor' AND LOWER(TRIM(email)) = :email"),
        {"email": email},
    )
    doc = result.fetchone()
    if not doc:
        await db.commit()
        raise HTTPException(status_code=404, detail="Врач не найден")

    await db.execute(
        text("UPDATE users_profiles SET email_verified = TRUE WHERE user_id = :user_id"),
        {"user_id": doc[0]},
    )
    await db.commit()

    return AuthResponse(
        success=True,
        user_id=doc[0],
        role="doctor",
        full_name=doc[1],
        message="Почта подтверждена",
    )


@router.post("/login", response_model=AuthResponse)
async def login_doctor(data: DoctorLoginRequest, db: AsyncSession = Depends(get_db)):
    """Doctor login with email + password. If the email was never verified,
    re-send a code and ask the client to verify (code is needed only once)."""
    email = (data.email or "").strip().lower()
    password = (data.password or "").strip()

    if not email:
        raise HTTPException(status_code=400, detail="Введите почту")
    if not password:
        raise HTTPException(status_code=400, detail="Введите пароль")

    result = await db.execute(
        text("SELECT user_id, full_name, phone, email_verified FROM users_profiles WHERE role = 'doctor' AND LOWER(TRIM(email)) = :email"),
        {"email": email},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Врач с такой почтой не найден")
    if (row[2] or "") != password:
        raise HTTPException(status_code=401, detail="Неверный пароль")

    if not row[3]:
        # Never verified — issue a fresh code and route the client to verification.
        code = await issue_code(db, email, "doctor_verify")
        await db.commit()
        await asyncio.to_thread(send_code_email, email, code, "doctor_verify")
        return AuthResponse(
            success=True,
            needs_verification=True,
            email=email,
            message="Требуется подтверждение почты",
        )

    return AuthResponse(
        success=True,
        user_id=row[0],
        role="doctor",
        full_name=row[1],
        message="Успешный вход",
    )


# ---------------------------------------------------------------------------
# Patient login via emailed code (#4)
# ---------------------------------------------------------------------------
@router.post("/patient/request-code", response_model=AuthResponse)
async def patient_request_code(data: PatientRequestCodeRequest, db: AsyncSession = Depends(get_db)):
    """A patient enters the email their doctor registered; we email a login code."""
    email = (data.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Введите корректную почту")

    result = await db.execute(
        text("SELECT user_id FROM users_profiles WHERE role = 'patient' AND LOWER(TRIM(email)) = :email"),
        {"email": email},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Аккаунт с такой почтой не найден. Обратитесь к вашему врачу.")

    code = await issue_code(db, email, "patient_login")
    await db.commit()
    await asyncio.to_thread(send_code_email, email, code, "patient_login")

    return AuthResponse(success=True, needs_verification=True, email=email, message="Код отправлен на почту")


@router.post("/patient/verify-code", response_model=AuthResponse)
async def patient_verify_code(data: PatientVerifyCodeRequest, db: AsyncSession = Depends(get_db)):
    """Verify the patient's login code and start a session."""
    email = (data.email or "").strip().lower()

    ok = await verify_code(db, email, data.code, "patient_login")
    if not ok:
        await db.commit()
        raise HTTPException(status_code=400, detail="Неверный или просроченный код")

    result = await db.execute(
        text("SELECT user_id, full_name, birth_date FROM users_profiles WHERE role = 'patient' AND LOWER(TRIM(email)) = :email"),
        {"email": email},
    )
    pat = result.fetchone()
    if not pat:
        await db.commit()
        raise HTTPException(status_code=404, detail="Пациент не найден")
    await db.commit()

    return AuthResponse(
        success=True,
        user_id=pat[0],
        role="patient",
        full_name=pat[1],
        birth_date=str(pat[2]) if pat[2] else None,
        message="Успешный вход",
    )
