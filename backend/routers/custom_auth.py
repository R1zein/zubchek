import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/custom-auth", tags=["custom-auth"])


class LoginRequest(BaseModel):
    role: str  # "doctor" or "patient"
    full_name: Optional[str] = None  # For doctor login
    login: Optional[str] = None  # For patient login
    password: str


class LoginResponse(BaseModel):
    success: bool
    user_id: str
    role: str
    full_name: str
    message: str
    birth_date: Optional[str] = None


class RegisterRequest(BaseModel):
    role: str
    full_name: str
    password: str
    clinic_password: Optional[str] = None  # For doctor registration
    patient_login: Optional[str] = None  # For patient registration


class RegisterResponse(BaseModel):
    success: bool
    user_id: str
    role: str
    full_name: str
    message: str


CLINIC_PASSWORD = "logtest121"


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Custom login - checks credentials in users_profiles table."""
    if data.role == "doctor":
        if not data.full_name:
            raise HTTPException(status_code=400, detail="ФИО обязательно для входа врача")

        # Find doctor by full_name and check password (stored in phone field)
        result = await db.execute(
            text("""
                SELECT user_id, full_name, phone
                FROM users_profiles
                WHERE role = 'doctor' AND LOWER(TRIM(full_name)) = LOWER(TRIM(:full_name))
            """),
            {"full_name": data.full_name},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Врач с таким ФИО не найден")

        stored_password = row[2]  # phone field stores password
        if stored_password != data.password:
            raise HTTPException(status_code=401, detail="Неверный пароль")

        return LoginResponse(
            success=True,
            user_id=row[0],
            role="doctor",
            full_name=row[1],
            message="Успешный вход",
        )

    elif data.role == "patient":
        if not data.login:
            raise HTTPException(status_code=400, detail="Логин обязателен для входа пациента")

        # Find patient by login (stored in clinic_name field) and check password (stored in phone field)
        result = await db.execute(
            text("""
                SELECT user_id, full_name, phone, birth_date
                FROM users_profiles
                WHERE role = 'patient' AND LOWER(TRIM(clinic_name)) = LOWER(TRIM(:login))
            """),
            {"login": data.login},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Пациент с таким логином не найден")

        stored_password = row[2]  # phone field stores password

        if not stored_password or stored_password.strip() == "":
            raise HTTPException(status_code=401, detail="Пароль не установлен. Обратитесь к вашему врачу.")

        if stored_password != data.password:
            raise HTTPException(status_code=401, detail="Неверный пароль")

        return LoginResponse(
            success=True,
            user_id=row[0],
            role="patient",
            full_name=row[1],
            message="Успешный вход",
            birth_date=str(row[3]) if row[3] else None,
        )

    else:
        raise HTTPException(status_code=400, detail="Неверная роль")


@router.post("/register", response_model=RegisterResponse)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Custom registration - creates user profile in DB."""
    import uuid

    if not data.full_name.strip():
        raise HTTPException(status_code=400, detail="ФИО обязательно")
    if not data.password.strip():
        raise HTTPException(status_code=400, detail="Пароль обязателен")

    if data.role == "doctor":
        if data.clinic_password != CLINIC_PASSWORD:
            raise HTTPException(status_code=403, detail="Неверный специальный пароль")

        # Check if doctor with same name already exists
        existing = await db.execute(
            text("SELECT user_id FROM users_profiles WHERE role = 'doctor' AND LOWER(TRIM(full_name)) = LOWER(TRIM(:full_name))"),
            {"full_name": data.full_name.strip()},
        )
        if existing.fetchone():
            raise HTTPException(status_code=409, detail="Врач с таким ФИО уже зарегистрирован")

        user_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO users_profiles (user_id, role, full_name, phone)
                VALUES (:user_id, 'doctor', :full_name, :password)
            """),
            {"user_id": user_id, "full_name": data.full_name.strip(), "password": data.password.strip()},
        )
        await db.commit()

        return RegisterResponse(
            success=True,
            user_id=user_id,
            role="doctor",
            full_name=data.full_name.strip(),
            message="Регистрация успешна",
        )

    elif data.role == "patient":
        if not data.patient_login or not data.patient_login.strip():
            raise HTTPException(status_code=400, detail="Логин обязателен для пациента")

        # Check if patient with same login already exists
        existing = await db.execute(
            text("SELECT user_id FROM users_profiles WHERE role = 'patient' AND LOWER(TRIM(clinic_name)) = LOWER(TRIM(:login))"),
            {"login": data.patient_login.strip()},
        )
        if existing.fetchone():
            raise HTTPException(status_code=409, detail="Пациент с таким логином уже зарегистрирован")

        user_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO users_profiles (user_id, role, full_name, clinic_name, phone)
                VALUES (:user_id, 'patient', :full_name, :login, :password)
            """),
            {"user_id": user_id, "full_name": data.full_name.strip(), "login": data.patient_login.strip(), "password": data.password.strip()},
        )
        await db.commit()

        return RegisterResponse(
            success=True,
            user_id=user_id,
            role="patient",
            full_name=data.full_name.strip(),
            message="Регистрация успешна",
        )

    else:
        raise HTTPException(status_code=400, detail="Неверная роль")


class SetPasswordRequest(BaseModel):
    login: str
    new_password: str


class SetPasswordResponse(BaseModel):
    success: bool
    user_id: str
    role: str
    full_name: str
    message: str
    birth_date: Optional[str] = None


@router.post("/set-password", response_model=SetPasswordResponse)
async def set_password(
    data: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set password for a patient who was registered by a doctor (first login)."""
    if not data.login.strip():
        raise HTTPException(status_code=400, detail="Логин обязателен")
    if not data.new_password.strip():
        raise HTTPException(status_code=400, detail="Пароль обязателен")

    # Find patient by login
    result = await db.execute(
        text("""
            SELECT user_id, full_name, phone, birth_date
            FROM users_profiles
            WHERE role = 'patient' AND LOWER(TRIM(clinic_name)) = LOWER(TRIM(:login))
        """),
        {"login": data.login.strip()},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Пациент с таким логином не найден")

    # Check that password is not already set
    stored_password = row[2]
    if stored_password and stored_password.strip() != "":
        raise HTTPException(status_code=400, detail="Пароль уже установлен. Используйте обычный вход.")

    # Set the password
    await db.execute(
        text("UPDATE users_profiles SET phone = :password WHERE user_id = :user_id"),
        {"password": data.new_password.strip(), "user_id": row[0]},
    )
    await db.commit()

    return SetPasswordResponse(
        success=True,
        user_id=row[0],
        role="patient",
        full_name=row[1],
        message="Пароль успешно установлен",
        birth_date=str(row[3]) if row[3] else None,
    )