from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas

router = APIRouter(prefix="/versions", tags=["Recommended Versions"])


@router.get("", response_model=list[schemas.RecommendedVersionOut])
def list_versions(db: Session = Depends(get_db)):
    return (
        db.query(models.RecommendedVersion)
        .order_by(models.RecommendedVersion.family.asc(), models.RecommendedVersion.id.asc())
        .all()
    )


@router.get("/{version_id}", response_model=schemas.RecommendedVersionOut)
def get_version(version_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(models.RecommendedVersion)
        .filter(models.RecommendedVersion.id == version_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Recommended version id={version_id} not found")
    return row


@router.post("", response_model=schemas.RecommendedVersionOut, status_code=201)
def create_version(payload: schemas.RecommendedVersionCreate, db: Session = Depends(get_db)):
    family = payload.family.strip().upper()
    version = payload.version.strip()

    if not family:
        raise HTTPException(status_code=400, detail="family is required")
    if not version:
        raise HTTPException(status_code=400, detail="version is required")

    if payload.is_recommended:
        (
            db.query(models.RecommendedVersion)
            .filter(models.RecommendedVersion.family == family)
            .update({"is_recommended": False}, synchronize_session=False)
        )

    row = models.RecommendedVersion(
        family=family,
        version=version,
        is_recommended=payload.is_recommended,
    )

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{version_id}", response_model=schemas.RecommendedVersionOut)
def update_version(
    version_id: int,
    payload: schemas.RecommendedVersionUpdate,
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.RecommendedVersion)
        .filter(models.RecommendedVersion.id == version_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Recommended version id={version_id} not found")

    family = payload.family.strip().upper()
    version = payload.version.strip()

    if not family:
        raise HTTPException(status_code=400, detail="family is required")
    if not version:
        raise HTTPException(status_code=400, detail="version is required")

    if payload.is_recommended:
        (
            db.query(models.RecommendedVersion)
            .filter(models.RecommendedVersion.family == family)
            .filter(models.RecommendedVersion.id != version_id)
            .update({"is_recommended": False}, synchronize_session=False)
        )

    row.family = family
    row.version = version
    row.is_recommended = payload.is_recommended

    db.commit()
    db.refresh(row)
    return row