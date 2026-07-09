import logging
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.database import get_db
from dependencies.custom_auth import get_current_user_custom as get_current_user
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/invite", tags=["invite"])


class GenerateCodeResponse(BaseModel):
    invite_code: str


class JoinDoctorRequest(BaseModel):
    invite_code: str


class JoinDoctorResponse(BaseModel):
    success: bool
    doctor_name: Optional[str] = None
    message: str


class PatientInfo(BaseModel):
    patient_id: str
    full_name: Optional[str] = None
    phone: Optional[str] = None


class DoctorPatientsResponse(BaseModel):
    patients: list


class PatientReportsResponse(BaseModel):
    reports: list


def generate_invite_code(length: int = 6) -> str:
    """Generate a random alphanumeric invite code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


@router.post("/generate", response_model=GenerateCodeResponse)
async def generate_code(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an invite code for a doctor to share with patients."""
    # Verify user is a doctor
    result = await db.execute(
        text("SELECT role FROM users_profiles WHERE user_id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row or row[0] != "doctor":
        raise HTTPException(status_code=403, detail="Только врачи могут генерировать коды приглашения")

    # Generate unique code
    code = generate_invite_code()

    # Save to doctor_patients with pending status
    await db.execute(
        text("""
            INSERT INTO doctor_patients (user_id, invite_code, status)
            VALUES (:doctor_id, :code, 'pending')
        """),
        {"doctor_id": str(current_user.id), "code": code},
    )
    await db.commit()

    return GenerateCodeResponse(invite_code=code)


@router.post("/join", response_model=JoinDoctorResponse)
async def join_doctor(
    data: JoinDoctorRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient joins a doctor using an invite code."""
    # Verify user is a patient
    result = await db.execute(
        text("SELECT role FROM users_profiles WHERE user_id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row or row[0] != "patient":
        raise HTTPException(status_code=403, detail="Только пациенты могут использовать коды приглашения")

    # Find the invite code
    invite_result = await db.execute(
        text("SELECT id, user_id FROM doctor_patients WHERE invite_code = :code AND status = 'pending'"),
        {"code": data.invite_code.upper()},
    )
    invite_row = invite_result.fetchone()
    if not invite_row:
        raise HTTPException(status_code=404, detail="Код приглашения не найден или уже использован")

    invite_id = invite_row[0]
    doctor_id = invite_row[1]

    # Check if already linked to this doctor
    existing = await db.execute(
        text("SELECT id FROM doctor_patients WHERE user_id = :doctor_id AND patient_id = :patient_id AND status = 'active'"),
        {"doctor_id": doctor_id, "patient_id": str(current_user.id)},
    )
    if existing.fetchone():
        raise HTTPException(status_code=400, detail="Вы уже привязаны к этому врачу")

    # Update the invite record
    await db.execute(
        text("UPDATE doctor_patients SET patient_id = :patient_id, status = 'active' WHERE id = :id"),
        {"patient_id": str(current_user.id), "id": invite_id},
    )
    await db.commit()

    # Get doctor name
    doctor_profile = await db.execute(
        text("SELECT full_name FROM users_profiles WHERE user_id = :user_id"),
        {"user_id": doctor_id},
    )
    doctor_row = doctor_profile.fetchone()
    doctor_name = doctor_row[0] if doctor_row else None

    return JoinDoctorResponse(
        success=True,
        doctor_name=doctor_name,
        message=f"Вы успешно привязаны к врачу{(' ' + doctor_name) if doctor_name else ''}",
    )


@router.get("/my-patients", response_model=DoctorPatientsResponse)
async def get_my_patients(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of patients for the current doctor."""
    result = await db.execute(
        text("""
            SELECT dp.patient_id, up.full_name, up.phone, up.birth_date, up.gender
            FROM doctor_patients dp
            LEFT JOIN users_profiles up ON dp.patient_id = up.user_id
            WHERE dp.user_id = :doctor_id AND dp.status = 'active'
        """),
        {"doctor_id": str(current_user.id)},
    )
    rows = result.fetchall()
    patients = [
        {
            "patient_id": row[0],
            "full_name": row[1],
            "phone": row[2],
            "birth_date": str(row[3]) if row[3] else None,
            "gender": row[4],
        }
        for row in rows
    ]
    return DoctorPatientsResponse(patients=patients)


@router.get("/patient-reports/{patient_id}", response_model=PatientReportsResponse)
async def get_patient_reports(
    patient_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get reports for a specific patient (doctor must be linked)."""
    # Verify doctor-patient relationship
    link = await db.execute(
        text("SELECT id FROM doctor_patients WHERE user_id = :doctor_id AND patient_id = :patient_id AND status = 'active'"),
        {"doctor_id": str(current_user.id), "patient_id": patient_id},
    )
    if not link.fetchone():
        raise HTTPException(status_code=403, detail="У вас нет доступа к отчётам этого пациента")

    result = await db.execute(
        text("""
            SELECT id, teeth_scores, php_index, hygiene_level, plaque_percentage, risk_level, plaque_types, recommendations, created_at, analysis_type, analysis_data
            FROM reports WHERE user_id = :patient_id ORDER BY created_at DESC
        """),
        {"patient_id": patient_id},
    )
    rows = result.fetchall()
    reports = []
    for row in rows:
        import json
        report_entry = {
            "id": row[0],
            "teeth_scores": json.loads(row[1]) if row[1] else None,
            "php_index": row[2],
            "hygiene_level": row[3],
            "plaque_percentage": row[4],
            "risk_level": row[5],
            "plaque_types": json.loads(row[6]) if row[6] else None,
            "recommendations": json.loads(row[7]) if row[7] else None,
            "created_at": str(row[8]) if row[8] else None,
            "analysis_type": row[9] if len(row) > 9 else None,
            "analysis_data": json.loads(row[10]) if len(row) > 10 and row[10] else None,
        }
        reports.append(report_entry)
    return PatientReportsResponse(reports=reports)


@router.delete("/delete-report/{report_id}")
async def delete_patient_report(
    report_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a patient report (only the linked doctor can delete)."""
    # Find the report and its owner
    report_row = await db.execute(
        text("SELECT user_id FROM reports WHERE id = :report_id"),
        {"report_id": report_id},
    )
    report = report_row.fetchone()
    if not report:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    patient_id = report[0]

    # Verify doctor-patient relationship
    link = await db.execute(
        text("SELECT id FROM doctor_patients WHERE user_id = :doctor_id AND patient_id = :patient_id AND status = 'active'"),
        {"doctor_id": str(current_user.id), "patient_id": patient_id},
    )
    if not link.fetchone():
        raise HTTPException(status_code=403, detail="У вас нет прав на удаление этого отчёта")

    await db.execute(
        text("DELETE FROM reports WHERE id = :report_id"),
        {"report_id": report_id},
    )
    await db.commit()
    return {"message": "Отчёт удалён", "report_id": report_id}


class RegisterPatientRequest(BaseModel):
    full_name: str
    login: str
    password: str
    birth_date: str
    gender: Optional[str] = None


class RegisterPatientResponse(BaseModel):
    patient_id: str
    full_name: str
    login: str
    password: str


@router.post("/register-patient", response_model=RegisterPatientResponse)
async def register_patient(
    data: RegisterPatientRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Doctor registers a new patient directly (creates profile and links them)."""
    import uuid

    # Verify user is a doctor
    result = await db.execute(
        text("SELECT role FROM users_profiles WHERE user_id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row or row[0] != "doctor":
        raise HTTPException(status_code=403, detail="Только врачи могут регистрировать пациентов")

    # Check if patient login already exists
    existing = await db.execute(
        text("SELECT user_id FROM users_profiles WHERE role = 'patient' AND LOWER(TRIM(clinic_name)) = LOWER(TRIM(:login))"),
        {"login": data.login},
    )
    if existing.fetchone():
        raise HTTPException(status_code=409, detail="Пациент с таким логином уже существует")

    # Validate birth_date is provided and valid
    if not data.birth_date or not data.birth_date.strip():
        raise HTTPException(status_code=422, detail="Дата рождения обязательна")

    # Generate a unique patient_id
    patient_id = str(uuid.uuid4())

    # Parse birth_date string to date object
    from datetime import date as date_type
    parsed_birth_date = None
    try:
        parts = data.birth_date.split("-")
        parsed_birth_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        raise HTTPException(status_code=422, detail="Неверный формат даты рождения")

    try:
        # Create a patient profile with clinic_name=login, phone=password, birth_date, gender
        if parsed_birth_date:
            await db.execute(
                text("""
                    INSERT INTO users_profiles (user_id, role, full_name, clinic_name, phone, birth_date, gender)
                    VALUES (:user_id, 'patient', :full_name, :login, :password, :birth_date, :gender)
                """),
                {
                    "user_id": patient_id,
                    "full_name": data.full_name,
                    "login": data.login,
                    "password": data.password,
                    "birth_date": parsed_birth_date,
                    "gender": data.gender,
                },
            )
        else:
            await db.execute(
                text("""
                    INSERT INTO users_profiles (user_id, role, full_name, clinic_name, phone, gender)
                    VALUES (:user_id, 'patient', :full_name, :login, :password, :gender)
                """),
                {
                    "user_id": patient_id,
                    "full_name": data.full_name,
                    "login": data.login,
                    "password": data.password,
                    "gender": data.gender,
                },
            )

        # Link patient to doctor
        await db.execute(
            text("""
                INSERT INTO doctor_patients (user_id, patient_id, status, invite_code)
                VALUES (:doctor_id, :patient_id, 'active', :login)
            """),
            {"doctor_id": str(current_user.id), "patient_id": patient_id, "login": data.login},
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error registering patient: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при регистрации пациента: {str(e)}")

    return RegisterPatientResponse(
        patient_id=patient_id,
        full_name=data.full_name,
        login=data.login,
        password=data.password,
    )


class AssignReportRequest(BaseModel):
    report_id: int
    patient_id: str


class AssignReportResponse(BaseModel):
    success: bool
    message: str


@router.post("/assign-report", response_model=AssignReportResponse)
async def assign_report_to_patient(
    data: AssignReportRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a report to a patient (doctor reassigns the report's user_id)."""
    # Verify user is a doctor
    result = await db.execute(
        text("SELECT role FROM users_profiles WHERE user_id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row or row[0] != "doctor":
        raise HTTPException(status_code=403, detail="Только врачи могут назначать отчёты пациентам")

    # Verify doctor-patient relationship
    link = await db.execute(
        text("SELECT id FROM doctor_patients WHERE user_id = :doctor_id AND patient_id = :patient_id AND status = 'active'"),
        {"doctor_id": str(current_user.id), "patient_id": data.patient_id},
    )
    if not link.fetchone():
        raise HTTPException(status_code=403, detail="Пациент не привязан к вам")

    # Update the report's user_id to the patient
    update_result = await db.execute(
        text("UPDATE reports SET user_id = :patient_id WHERE id = :report_id"),
        {"patient_id": data.patient_id, "report_id": data.report_id},
    )
    await db.commit()

    if update_result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Отчёт не найден")

    return AssignReportResponse(success=True, message="Отчёт успешно привязан к пациенту")


class DeletePatientResponse(BaseModel):
    success: bool
    message: str


@router.delete("/delete-patient/{patient_id}", response_model=DeletePatientResponse)
async def delete_patient(
    patient_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a patient and all associated data (reports, doctor_patients link, profile)."""
    # Verify user is a doctor
    result = await db.execute(
        text("SELECT role FROM users_profiles WHERE user_id = :user_id"),
        {"user_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row or row[0] != "doctor":
        raise HTTPException(status_code=403, detail="Только врачи могут удалять пациентов")

    # Verify doctor-patient relationship
    link = await db.execute(
        text("SELECT id FROM doctor_patients WHERE user_id = :doctor_id AND patient_id = :patient_id AND status = 'active'"),
        {"doctor_id": str(current_user.id), "patient_id": patient_id},
    )
    if not link.fetchone():
        raise HTTPException(status_code=403, detail="Пациент не привязан к вам")

    try:
        # Delete all reports for this patient
        await db.execute(
            text("DELETE FROM reports WHERE user_id = :patient_id"),
            {"patient_id": patient_id},
        )

        # Delete doctor_patients link
        await db.execute(
            text("DELETE FROM doctor_patients WHERE patient_id = :patient_id"),
            {"patient_id": patient_id},
        )

        # Delete patient profile
        await db.execute(
            text("DELETE FROM users_profiles WHERE user_id = :patient_id AND role = 'patient'"),
            {"patient_id": patient_id},
        )

        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting patient: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при удалении пациента")

    return DeletePatientResponse(success=True, message="Пациент и все связанные данные удалены")


@router.get("/my-reports")
async def get_my_reports(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all reports for the current user."""
    import json
    result = await db.execute(
        text("""
            SELECT id, teeth_scores, php_index, hygiene_level, plaque_percentage, risk_level, plaque_types, recommendations, image_data, created_at, analysis_type, analysis_data
            FROM reports WHERE user_id = :user_id ORDER BY created_at DESC
        """),
        {"user_id": str(current_user.id)},
    )
    rows = result.fetchall()
    reports = []
    for row in rows:
        reports.append({
            "id": row[0],
            "teeth_scores": json.loads(row[1]) if row[1] else None,
            "php_index": row[2],
            "hygiene_level": row[3],
            "plaque_percentage": row[4],
            "risk_level": row[5],
            "plaque_types": json.loads(row[6]) if row[6] else None,
            "recommendations": json.loads(row[7]) if row[7] else None,
            "image_data": row[8],
            "created_at": str(row[9]) if row[9] else None,
            "analysis_type": row[10] if len(row) > 10 else None,
            "analysis_data": json.loads(row[11]) if len(row) > 11 and row[11] else None,
        })
    return {"reports": reports}


@router.get("/my-doctor")
async def get_my_doctor(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the doctor linked to the current patient."""
    result = await db.execute(
        text("""
            SELECT dp.user_id, up.full_name, up.clinic_name
            FROM doctor_patients dp
            LEFT JOIN users_profiles up ON dp.user_id = up.user_id
            WHERE dp.patient_id = :patient_id AND dp.status = 'active'
            LIMIT 1
        """),
        {"patient_id": str(current_user.id)},
    )
    row = result.fetchone()
    if not row:
        return {"doctor": None}
    return {"doctor": {"id": row[0], "full_name": row[1], "clinic_name": row[2]}}