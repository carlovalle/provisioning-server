from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base
from sqlalchemy import Boolean

class Switch(Base):
    __tablename__ = "switches"
    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String, unique=True, index=True)
    model = Column(String)
    family = Column(String, nullable=True)
    current_version = Column(String)
    recommended_version = Column(String)
    state = Column(String, default="staging")
    staging_config = Column(String, nullable=True)
    final_config = Column(String, nullable=True)
    mgmt_ip = Column(String, nullable=True)
    last_seen_ip = Column(String, nullable=True)
    reachable = Column(Boolean, nullable=False, default=False)



class RecommendedVersion(Base):
    __tablename__ = "recommended_versions"
    id = Column(Integer, primary_key=True)
    family = Column(String, unique=True, index=True)
    version = Column(String)


class ProvisioningLog(Base):
    __tablename__ = "provisioning_logs"
    id = Column(Integer, primary_key=True)
    serial_number = Column(String)
    event = Column(String)
    timestamp = Column(DateTime, server_default=func.now())