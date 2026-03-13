from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models, schemas
from database import get_db

router = APIRouter(prefix="/images", tags=["images"])


@router.post("", response_model=schemas.ImageOut)
def create_image(payload: schemas.ImageCreate, db: Session = Depends(get_db)):

    family = payload.family.upper().strip()
    version = payload.version.strip()
    filename = payload.filename.strip()

    existing = (
        db.query(models.ImageCatalog)
        .filter(models.ImageCatalog.family == family)
        .filter(models.ImageCatalog.version == version)
        .first()
    )

    if existing:
        existing.filename = filename
        db.commit()
        db.refresh(existing)
        return existing

    row = models.ImageCatalog(
        family=family,
        version=version,
        filename=filename
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return row


@router.get("", response_model=list[schemas.ImageOut])
def list_images(db: Session = Depends(get_db)):
    return db.query(models.ImageCatalog).all()