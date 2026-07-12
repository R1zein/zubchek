from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String


class Users_profiles(Base):
    __tablename__ = "users_profiles"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    clinic_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    # Email login: doctors log in with email+password; patients log in with an
    # emailed one-time code. Nullable so patients registered without an email
    # (no account) and pre-existing rows keep working. Auto-added on startup by
    # the table-repair step in core/database.py.
    email = Column(String, nullable=True)
    email_verified = Column(Boolean, nullable=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)