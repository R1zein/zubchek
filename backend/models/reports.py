from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text


class Reports(Base):
    __tablename__ = "reports"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=True)
    teeth_scores = Column(String, nullable=True)
    php_index = Column(Float, nullable=True)
    hygiene_level = Column(String, nullable=True)
    plaque_percentage = Column(Integer, nullable=True)
    risk_level = Column(String, nullable=True)
    plaque_types = Column(String, nullable=True)
    recommendations = Column(String, nullable=True)
    image_data = Column(String, nullable=True)
    analysis_type = Column(String, nullable=True)  # "fedorov_volodkina" or "adult_indices"
    analysis_data = Column(Text, nullable=True)  # Full JSON of analysis result
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)