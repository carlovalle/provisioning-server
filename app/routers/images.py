from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import models, schemas
from database import get_db
from datetime import datetime

router = APIRouter(prefix="/images", tags=["images"])

IMAGE_ROOT_DIR = os.getenv("IMAGE_ROOT_DIR", "/app/images")



def _safe_family_path(family: str) -> str:
    family_clean = family.strip().lower()
    if not family_clean:
        raise HTTPException(status_code=400, detail="family is required")

    path = os.path.join(IMAGE_ROOT_DIR, family_clean)
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail=f"Family folder not found: {family_clean}")
    return path


def _safe_file_path(family: str, filename: str) -> str:
    family_path = _safe_family_path(family)
    file_path = os.path.join(family_path, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    return file_path


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

def _safe_family_path(family: str) -> str:
    family_clean = family.strip().lower()
    if not family_clean:
        raise HTTPException(status_code=400, detail="family is required")

    path = os.path.join(IMAGE_ROOT_DIR, family_clean)
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail=f"Family folder not found: {family_clean}")
    return path


def _safe_file_path(family: str, filename: str) -> str:
    family_path = _safe_family_path(family)
    file_path = os.path.join(family_path, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    return file_path


@router.get("/families")
def list_image_families():
    if not os.path.isdir(IMAGE_ROOT_DIR):
        raise HTTPException(status_code=404, detail="Image root directory not found")

    families = sorted(
        name for name in os.listdir(IMAGE_ROOT_DIR)
        if os.path.isdir(os.path.join(IMAGE_ROOT_DIR, name))
    )
    return {"families": families}


@router.get("/files/{family}")
def list_images_by_family(family: str, db: Session = Depends(get_db)):
    family_path = _safe_family_path(family)
    family_db = family.strip().upper()

    db_rows = (
        db.query(models.RecommendedVersion)
        .filter(models.RecommendedVersion.family == family_db)
        .all()
    )

    db_map = {
        row.filename: {
            "version": row.version,
            "is_recommended": row.is_recommended,
            "id": row.id,
        }
        for row in db_rows
        if row.filename
    }

    files = []
    for name in sorted(os.listdir(family_path)):
        full_path = os.path.join(family_path, name)
        if os.path.isfile(full_path):
            stat = os.stat(full_path)
            match = db_map.get(name)

            files.append({
                "filename": name,
                "size": stat.st_size,
                "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                "version": match["version"] if match else None,
                "is_recommended": match["is_recommended"] if match else False,
                "recommended_version_id": match["id"] if match else None,
            })

    return {
        "family": family.strip().lower(),
        "files": files,
    }

@router.post("/upload/{family}")
def upload_image_file(
    family: str,
    file: UploadFile = File(...),
    version: str = Form(...),
    is_recommended: bool = Form(False),
    db: Session = Depends(get_db),
):
    family_clean = family.strip().lower()
    family_db = family.strip().upper()

    if not family_clean:
        raise HTTPException(status_code=400, detail="family is required")

    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    version_clean = version.strip()
    if not version_clean:
        raise HTTPException(status_code=400, detail="version is required")

    allowed_ext = (".bin", ".tar", ".txt", ".sha256", ".md5")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(status_code=400, detail="Invalid file type")

    family_path = os.path.join(IMAGE_ROOT_DIR, family_clean)
    os.makedirs(family_path, exist_ok=True)

    dest_path = os.path.join(family_path, file.filename)

    # evitar duplicado exacto en DB por family + filename
    existing = (
        db.query(models.RecommendedVersion)
        .filter(models.RecommendedVersion.family == family_db)
        .filter(models.RecommendedVersion.filename == file.filename)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"File '{file.filename}' already exists in recommended_versions for family {family_db}",
        )

    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        if is_recommended:
            (
                db.query(models.RecommendedVersion)
                .filter(models.RecommendedVersion.family == family_db)
                .update({"is_recommended": False}, synchronize_session=False)
            )

        row = models.RecommendedVersion(
            family=family_db,
            version=version_clean,
            is_recommended=is_recommended,
            filename=file.filename,
        )

        db.add(row)
        db.commit()
        db.refresh(row)

        stat = os.stat(dest_path)

        return {
            "id": row.id,
            "family": family_clean,
            "family_db": family_db,
            "filename": file.filename,
            "version": row.version,
            "is_recommended": row.is_recommended,
            "size": stat.st_size,
            "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            "path": dest_path,
        }

    except HTTPException:
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise
    except Exception as e:
        db.rollback()
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}")
    finally:
        try:
            file.file.close()
        except Exception:
            pass

@router.get("/download/{family}/{filename}")
def download_image_file(family: str, filename: str):
    file_path = _safe_file_path(family, filename)
    return FileResponse(file_path, filename=filename)