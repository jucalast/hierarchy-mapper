from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from core.database import Base

class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True, index=True)
    pipedrive_id = Column(Integer, unique=True, index=True)
    name = Column(String, index=True)
    cnpj = Column(String, unique=True, index=True, nullable=True)
    domain = Column(String, index=True, nullable=True)
    address = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, index=True)
    category = Column(String, nullable=True) # Ex: "Compras", "Logística"
    product_focus = Column(String, nullable=True) # Ex: "Embalagens", "TI"
    linkedin_url = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    is_excluded = Column(Integer, server_default="0") # 1 = Excluída/Oculta
    source = Column(String, default="pipedrive") # Ex: pipedrive, outlook, manual
    last_enrichment = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
