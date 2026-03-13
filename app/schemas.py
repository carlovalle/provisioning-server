from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SwitchCreate(BaseModel):
    serial_number: str


class ReportVersion(BaseModel):
    serial_number: str
    current_version: str
    model: Optional[str] = None


class SwitchOut(BaseModel):
    id: int
    serial_number: str

    model: Optional[str] = None
    family: Optional[str] = None

    current_version: Optional[str] = None
    recommended_version: Optional[str] = None

    state: str

    mgmt_ip: Optional[str] = None
    last_seen_ip: Optional[str] = None
    reachable: bool = False

    last_reachability_check: Optional[datetime] = None

    class Config:
        orm_mode = True

class RecommendedVersionCreate(BaseModel):
    family: str
    version: str


class RecommendedVersionOut(BaseModel):
    id: int
    family: str
    version: str

    class Config:
        orm_mode = True

class ReportIP(BaseModel):
    serial_number: str
    last_seen_ip: str
    mgmt_ip: Optional[str] = None

class ImageCreate(BaseModel):
    family: str
    version: str
    filename: str


class ImageOut(BaseModel):
    id: int
    family: str
    version: str
    filename: str
    created_at: datetime

    class Config:
        orm_mode = True
class UpgradePlanOut(BaseModel):
    serial_number: str
    family: str
    current_version: Optional[str] = None
    recommended_version: str
    filename: str
    image_url: str
    mgmt_ip: Optional[str] = None
    reachable: bool
    state: str