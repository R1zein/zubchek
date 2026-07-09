from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Doctor_patients(Base):
    __tablename__ = "doctor_patients"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    patient_id = Column(String, nullable=True)
    invite_code = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)