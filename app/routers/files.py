import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import schemas

router = APIRouter(prefix="/files", tags=["files"])

DAY0_DIR = os.getenv("DAY0_DIR", "/Open_PnP_Server/configs")
DAY0_TEMPLATES_DIR = os.getenv("DAY0_TEMPLATES_DIR", "/Open_PnP_Server/configs/templates")
DAYN_VARS_DIR = os.getenv("DAYN_VARS_DIR", "/data/vars/dayn")
DAYN_TEMPLATES_DIR = os.getenv("DAYN_TEMPLATES_DIR", "/data/templates/dayn")


def _read_text_file(path: str) -> str:
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text_file(path: str, content: str) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


@router.get("/day0-config/{serial}", response_model=schemas.FileContentOut)
def get_day0_config(serial: str):
    path = os.path.join(DAY0_DIR, f"{serial}.cfg")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/day0-config/{serial}", response_model=schemas.FileContentOut)
def put_day0_config(serial: str, payload: schemas.FileContentUpdate):
    path = os.path.join(DAY0_DIR, f"{serial}.cfg")
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}


@router.get("/day0-template", response_model=schemas.FileContentOut)
def get_day0_template():
    path = os.path.join(DAY0_TEMPLATES_DIR, "template.j2")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/day0-template", response_model=schemas.FileContentOut)
def put_day0_template(payload: schemas.FileContentUpdate):
    path = os.path.join(DAY0_TEMPLATES_DIR, "template.j2")
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}


@router.get("/dayn-vars/{serial}", response_model=schemas.FileContentOut)
def get_dayn_vars(serial: str):
    path = os.path.join(DAYN_VARS_DIR, f"{serial}.yml")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/dayn-vars/{serial}", response_model=schemas.FileContentOut)
def put_dayn_vars(serial: str, payload: schemas.FileContentUpdate):
    path = os.path.join(DAYN_VARS_DIR, f"{serial}.yml")
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}


@router.get("/dayn-template/base", response_model=schemas.FileContentOut)
def get_dayn_template_base():
    path = os.path.join(DAYN_TEMPLATES_DIR, "template_access_base.j2")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/dayn-template/base", response_model=schemas.FileContentOut)
def put_dayn_template_base(payload: schemas.FileContentUpdate):
    path = os.path.join(DAYN_TEMPLATES_DIR, "template_access_base.j2")
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}


@router.get("/dayn-template/nac", response_model=schemas.FileContentOut)
def get_dayn_template_nac():
    path = os.path.join(DAYN_TEMPLATES_DIR, "template_access_nac.j2")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/dayn-template/nac", response_model=schemas.FileContentOut)
def put_dayn_template_nac(payload: schemas.FileContentUpdate):
    path = os.path.join(DAYN_TEMPLATES_DIR, "template_access_nac.j2")
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}


@router.get("/dayn-template/aaa-final", response_model=schemas.FileContentOut)
def get_dayn_template_aaa_final():
    path = os.path.join(DAYN_TEMPLATES_DIR, "template_access_aaa_final.j2")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/dayn-template/aaa-final", response_model=schemas.FileContentOut)
def put_dayn_template_aaa_final(payload: schemas.FileContentUpdate):
    path = os.path.join(DAYN_TEMPLATES_DIR, "template_access_aaa_final.j2")
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}