from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Email_codes(Base):
    """One-time email verification / login codes.

    Used for two purposes (see the ``purpose`` column):
      - ``doctor_verify``  — confirm a doctor's email once after registration.
      - ``patient_login``  — log a patient in (they have no password).

    Rows are short-lived: a new code for the same (email, purpose) replaces the
    old one, and codes are deleted once used or expired. Created automatically
    on startup by ``Base.metadata.create_all`` (see core/database.py).
    """

    __tablename__ = "email_codes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    email = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False)
    purpose = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
