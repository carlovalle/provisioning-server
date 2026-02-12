from pydantic import BaseModel
from typing import Optional


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
