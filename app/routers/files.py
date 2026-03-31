import os
from fastapi import APIRouter, HTTPException
import schemas

router = APIRouter(prefix="/files", tags=["files"])

DAY0_DIR = os.getenv("DAY0_DIR", "/Open_PnP_Server/configs")
DAY0_TEMPLATES_DIR = os.getenv("DAY0_TEMPLATES_DIR", "/Open_PnP_Server/configs/templates")
DAYN_VARS_DIR = os.getenv("DAYN_VARS_DIR", "/data/vars/dayn")
DAYN_TEMPLATES_DIR = os.getenv("DAYN_TEMPLATES_DIR", "/data/templates/dayn")
DAYN_LOGS_DIR = os.getenv("DAYN_LOGS_DIR", "/data/logs")

ROLE_STAGE_TEMPLATES = {
    "access": {
        "base": "template_access_base.j2",
        "nac": "template_access_nac.j2",
        "aaa-final": "template_access_aaa_final.j2",
    },
    "backbone": {
        "base": "template_core_base.j2",
        # "nac": "template_core_nac.j2",
        "aaa-final": "template_core_aaa_final.j2",
    },
    "wan": {
        "base": "template_WAN_base.j2",
        "interfaces": "template_WAN_interfaces.j2",
        "aaa-final": "template_WAN_aaa_final.j2",
    },
}


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


def _normalize_role(role: str) -> str:
    value = role.strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail="role is required")
    return value


def _normalize_stage(stage: str) -> str:
    value = stage.strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail="stage is required")
    return value


def _resolve_dayn_template_path(role: str, stage: str) -> str:
    normalized_role = _normalize_role(role)
    normalized_stage = _normalize_stage(stage)

    role_templates = ROLE_STAGE_TEMPLATES.get(normalized_role)
    if not role_templates:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role}'. Valid roles: {sorted(ROLE_STAGE_TEMPLATES.keys())}",
        )

    filename = role_templates.get(normalized_stage)
    if not filename:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No template configured for role='{normalized_role}' "
                f"and stage='{normalized_stage}'"
            ),
        )

    return os.path.join(DAYN_TEMPLATES_DIR, filename)


def _resolve_serial_log_path(serial: str, log_name: str) -> str:
    safe_serial = serial.strip()
    if not safe_serial:
        raise HTTPException(status_code=400, detail="serial is required")
    filename = f"{safe_serial}_{log_name}.log"
    return os.path.join(DAYN_LOGS_DIR, filename)


def _resolve_dayn_log_path(serial: str, stage: str) -> str:
    normalized_stage = _normalize_stage(stage)
    safe_serial = serial.strip()

    allowed_stages = {"base", "nac", "interfaces", "aaa-final"}
    if normalized_stage not in allowed_stages:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage '{stage}'. Valid stages: {sorted(allowed_stages)}",
        )

    filename = f"{safe_serial}_dayn_{normalized_stage.replace('-', '_')}.log"
    return os.path.join(DAYN_LOGS_DIR, filename)

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


@router.get("/dayn-template/{role}/{stage}", response_model=schemas.FileContentOut)
def get_dayn_template(role: str, stage: str):
    path = _resolve_dayn_template_path(role, stage)
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.put("/dayn-template/{role}/{stage}", response_model=schemas.FileContentOut)
def put_dayn_template(role: str, stage: str, payload: schemas.FileContentUpdate):
    path = _resolve_dayn_template_path(role, stage)
    _write_text_file(path, payload.content)
    return {"path": path, "content": payload.content}


@router.get("/events-log/{serial}", response_model=schemas.FileContentOut)
def get_events_log(serial: str):
    path = _resolve_serial_log_path(serial, "events")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.get("/day0-log/{serial}", response_model=schemas.FileContentOut)
def get_day0_log(serial: str):
    path = _resolve_serial_log_path(serial, "day0")
    content = _read_text_file(path)
    return {"path": path, "content": content}


@router.get("/dayn-log/{serial}/{stage}", response_model=schemas.FileContentOut)
def get_dayn_log(serial: str, stage: str):
    path = _resolve_dayn_log_path(serial, stage)
    content = _read_text_file(path)
    return {"path": path, "content": content}