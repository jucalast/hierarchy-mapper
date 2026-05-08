from sqlalchemy import Column, String, JSON
from core.database import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True)
    category = Column(String, index=True, nullable=False)
    value = Column(JSON, nullable=False)
