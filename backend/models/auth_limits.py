from sqlalchemy import Column, Integer, String
from core.database import Base

class Auth_limits(Base):
    __tablename__ = 'auth_limits'
    key = Column(String, primary_key=True)
    hits = Column(Integer, nullable=False)
    expires = Column(Integer, nullable=False)
