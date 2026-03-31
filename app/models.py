from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from sqlalchemy.sql import func
from database import Base
from sqlalchemy import Boolean

class Switch(Base):
    __tablename__ = "switches"
    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String, unique=True, index=True)
    model = Column(String)
    family = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    role = Column(String, nullable=True) 
    current_version = Column(String)
    recommended_version = Column(String)
    state = Column(String, default="staging")
    staging_config = Column(String, nullable=True)
    final_config = Column(String, nullable=True)
    mgmt_ip = Column(String, nullable=True)
    last_seen_ip = Column(String, nullable=True)
    reachable = Column(Boolean, nullable=False, default=False)
    last_reachability_check = Column(DateTime, nullable=True)



class RecommendedVersion(Base):
    __tablename__ = "recommended_versions"
    id = Column(Integer, primary_key=True)
    family = Column(String, index=True)
    #family = Column(String, unique=True, index=True)
    version = Column(String)
    is_recommended = Column(Boolean, nullable=False, default=False)
    filename = Column(String, nullable=True)

class ProvisioningLog(Base):
    __tablename__ = "provisioning_logs"
    id = Column(Integer, primary_key=True)
    serial_number = Column(String)
    event = Column(String)
    timestamp = Column(DateTime, server_default=func.now())

class ImageCatalog(Base):
    __tablename__ = "image_catalog"

    id = Column(Integer, primary_key=True)
    family = Column(String, index=True, nullable=False)
    version = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # (opcional) si quieres evitar duplicados desde SQLAlchemy también:
    # __table_args__ = (UniqueConstraint("family", "version", name="ux_image_catalog_family_version"),)