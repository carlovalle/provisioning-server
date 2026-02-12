# routers/versions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import schemas

router = APIRouter(prefix="/versions", tags=["Recommended Versions"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[schemas.RecommendedVersionOut])
def list_versions(db: Session = Depends(get_db)):
    return db.query(models.RecommendedVersion).all()

@router.post("/", response_model=schemas.RecommendedVersionOut)
def upsert_version(payload: schemas.RecommendedVersionCreate, db: Session = Depends(get_db)):
    fam = payload.family.strip().upper()

    existing = db.query(models.RecommendedVersion).filter(models.RecommendedVersion.family == fam).first()
    if existing:
        existing.version = payload.version.strip()
        db.commit()
        db.refresh(existing)
        return existing

    obj = models.RecommendedVersion(family=fam, version=payload.version.strip())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
