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
    brand: Optional[str] = None
    role: Optional[str] = None
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
    is_recommended: bool = False

class RecommendedVersionOut(BaseModel):
    id: int
    family: str
    version: str
    is_recommended: bool

    model_config = {
        "from_attributes": True
    }

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
class FileContentOut(BaseModel):
    path: str
    content: str


class FileContentUpdate(BaseModel):
    content: str

class SwitchMetadataUpdate(BaseModel):
    brand: Optional[str] = None
    role: Optional[str] = None

class SwitchUpdate(BaseModel):
    brand: Optional[str] = None
    role: Optional[str] = None
    mgmt_ip: Optional[str] = None
    recommended_version: Optional[str] = None
    state: Optional[str] = None
    model: Optional[str] = None
    family: Optional[str] = None

class RecommendedVersionUpdate(BaseModel):
    family: str
    version: str
    is_recommended: bool

class ImageFileOut(BaseModel):
    filename: str
    size: int
    modified_at: str
    version: str | None = None
    is_recommended: bool = False