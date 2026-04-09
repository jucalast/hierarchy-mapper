from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from core.database import Base

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    role = Column(String)
    department = Column(String, index=True, nullable=True) # Ex: "Compras", "Quadro Societário"
    seniority = Column(Integer, default=0)
    linkedin_url = Column(String, unique=True, index=True)
    profile_pic = Column(Text, nullable=True)
    email = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey("organizations.id"))
    manager_id = Column(String, nullable=True) # ID do gerente (pode ser "root_company" ou outro "node_ID")
    last_scanned = Column(DateTime(timezone=True), server_default=func.now())
