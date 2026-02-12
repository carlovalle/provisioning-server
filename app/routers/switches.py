# app/routers/switches.py
from __future__ import annotations

import os
import shutil
import socket
from datetime import datetime
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from netmiko import ConnectHandler

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from utils import detect_family


router = APIRouter(prefix="/switches", tags=["switches"])

# Day 0: folder served by the Open PnP Server (mounted from host)
DAY0_DIR = os.getenv("DAY0_DIR", "/Open_PnP_Server/configs")

# Day N: rendered/audit outputs stored in provisioning server (mounted via ./data:/data)
DAYN_DIR = os.getenv("DAYN_DIR", "/data/configs/final")

# Day N templates + vars
DAYN_TEMPLATES_DIR = os.getenv("DAYN_TEMPLATES_DIR", "/data/templates/dayn")
DAYN_VARS_DIR = os.getenv("DAYN_VARS_DIR", "/data/vars/dayn")

# SSH settings (used by Day N apply)
SWITCH_SSH_USER = os.getenv("SWITCH_SSH_USER", "")
SWITCH_SSH_PASS = os.getenv("SWITCH_SSH_PASS", "")
SWITCH_SSH_SECRET = os.getenv("SWITCH_SSH_SECRET", "")
SWITCH_DEVICE_TYPE = os.getenv("SWITCH_DEVICE_TYPE", "cisco_ios")


def _ensure_dirs() -> None:
    os.makedirs(DAY0_DIR, exist_ok=True)
    os.makedirs(DAYN_DIR, exist_ok=True)
    os.makedirs(DAYN_TEMPLATES_DIR, exist_ok=True)
    os.makedirs(DAYN_VARS_DIR, exist_ok=True)


def _log(db: Session, serial: str, event: str) -> None:
    db.add(models.ProvisioningLog(serial_number=serial, event=event, timestamp=datetime.utcnow()))
    db.commit()


def _tcp_check(host: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _push_config_via_ssh(host: str, config_path: str) -> None:
    if not SWITCH_SSH_USER or not SWITCH_SSH_PASS:
        raise RuntimeError("Missing SWITCH_SSH_USER/SWITCH_SSH_PASS env vars in provisioning_api container")

    device = {
        "device_type": SWITCH_DEVICE_TYPE,
        "host": host,
        "username": SWITCH_SSH_USER,
        "password": SWITCH_SSH_PASS,
        "secret": SWITCH_SSH_SECRET or None,
        "timeout": 20,
        "conn_timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 20,
    }

    conn = ConnectHandler(**device)
    try:
        if SWITCH_SSH_SECRET:
            conn.enable()
        conn.send_config_from_file(config_file=config_path)
        conn.save_config()
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


def _read_yaml_vars_for_serial(serial: str) -> dict:
    path = os.path.join(DAYN_VARS_DIR, f"{serial}.yml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Vars file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("YAML must be an object (key: value) at top level")

    return data


def _render_template(template_name: str, context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(DAYN_TEMPLATES_DIR),
        undefined=StrictUndefined,  # si falta variable => falla
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template(template_name)
    return tpl.render(**context)


# ---------------- Core endpoints ----------------

@router.get("", response_model=list[schemas.SwitchOut])
def list_switches(db: Session = Depends(get_db)):
    return db.query(models.Switch).order_by(models.Switch.id.desc()).all()


@router.post("/register", response_model=schemas.SwitchOut, status_code=status.HTTP_201_CREATED)
def register_switch(payload: schemas.SwitchCreate, db: Session = Depends(get_db)):
    serial = payload.serial_number.strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial_number is required")

    existing = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Switch {serial} already registered")

    sw = models.Switch(
        serial_number=serial,
        model=None,
        family=None,
        current_version=None,
        recommended_version=None,
        state="non-connected",
        mgmt_ip=None,
        last_seen_ip=None,
        reachable=False,
    )
    db.add(sw)
    db.commit()
    db.refresh(sw)
    _log(db, serial, "registered")
    return sw


@router.post("/report-ip", response_model=schemas.SwitchOut)
def report_ip(payload: schemas.ReportIP, db: Session = Depends(get_db)):
    serial = payload.serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.last_seen_ip = payload.last_seen_ip.strip()

    # autopoblar mgmt_ip solo si aún no existe
    if not sw.mgmt_ip:
        sw.mgmt_ip = sw.last_seen_ip

    # si mandan mgmt_ip explícito, lo respetamos
    if payload.mgmt_ip:
        sw.mgmt_ip = payload.mgmt_ip.strip()

    db.commit()
    db.refresh(sw)
    _log(db, serial, f"reported-ip last_seen={sw.last_seen_ip} mgmt={sw.mgmt_ip}")
    return sw


@router.post("/set-mgmt-ip", response_model=schemas.SwitchOut)
def set_mgmt_ip(serial_number: str = Form(...), mgmt_ip: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.mgmt_ip = mgmt_ip.strip()
    db.commit()
    db.refresh(sw)
    _log(db, serial, f"set-mgmt-ip mgmt={sw.mgmt_ip}")
    return sw


@router.post("/check-reachable", response_model=schemas.SwitchOut)
def check_reachable(serial_number: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not sw.mgmt_ip:
        sw.reachable = False
    else:
        sw.reachable = _tcp_check(sw.mgmt_ip, port=22, timeout=2.0)

    db.commit()
    db.refresh(sw)
    _log(db, serial, f"reachability-check mgmt={sw.mgmt_ip} reachable={sw.reachable}")
    return sw


@router.post("/report-version", response_model=schemas.SwitchOut)
def report_version(payload: schemas.ReportVersion, db: Session = Depends(get_db)):
    serial = payload.serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.current_version = payload.current_version.strip()
    if payload.model is not None:
        sw.model = payload.model.strip() if payload.model else None

    fam: Optional[str] = detect_family(sw.model) if sw.model else None
    sw.family = fam

    rec = None
    if fam:
        rec_row = (
            db.query(models.RecommendedVersion)
            .filter(models.RecommendedVersion.family == fam)
            .order_by(models.RecommendedVersion.id.desc())
            .first()
        )
        if rec_row:
            rec = rec_row.version
    sw.recommended_version = rec

    if sw.recommended_version and sw.current_version:
        sw.state = "compliant" if sw.current_version == sw.recommended_version else "non-compliant"
    else:
        sw.state = "staging"

    db.commit()
    db.refresh(sw)
    _log(db, serial, f"reported-version model={sw.model} current={sw.current_version} family={fam} recommended={sw.recommended_version} state={sw.state}")
    return sw


@router.post("/config-applied", response_model=schemas.SwitchOut)
def config_applied(serial_number: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.state = "configured"
    db.commit()
    db.refresh(sw)
    _log(db, serial, "config-applied")
    return sw


@router.post("/upload-config", response_model=schemas.SwitchOut)
def upload_day0_config(serial_number: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Day 0 upload (multipart):
    - ServiceNow sube el archivo ya listo.
    - Se guarda DIRECTO en /Open_PnP_Server/configs/<SERIAL>.cfg
    """
    _ensure_dirs()
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found (register first)")

    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    day0_path = os.path.join(DAY0_DIR, f"{serial}.cfg")

    try:
        with open(day0_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write Day0 config: {e}")
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    sw.state = "staging"
    db.commit()
    db.refresh(sw)
    _log(db, serial, f"day0-uploaded path={day0_path}")
    return sw


@router.get("/ips/{serial_number}")
def get_switch_ips(serial_number: str, db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    return {"mgmt_ip": sw.mgmt_ip, "last_seen_ip": sw.last_seen_ip, "reachable": sw.reachable}


# ---------------- Day N endpoints ----------------

@router.post("/render-dayn-yaml", response_class=PlainTextResponse)
def render_dayn_yaml(serial_number: str = Form(...), template_name: str = Form(...), db: Session = Depends(get_db)):
    """
    Preview: renderiza /data/templates/dayn/<template> usando /data/vars/dayn/<SERIAL>.yml
    No hace SSH, no cambia state, no guarda archivo.
    """
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    try:
        vars_data = _read_yaml_vars_for_serial(serial)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML vars: {e}")

    context = {
        "serial_number": sw.serial_number,
        "model": sw.model,
        "family": getattr(sw, "family", None),
        "mgmt_ip": getattr(sw, "mgmt_ip", None),
        **vars_data,
    }

    try:
        rendered = _render_template(template_name, context)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template render failed: {e}")

    return rendered.strip() + "\n"


@router.post("/apply-dayn-yaml", response_model=schemas.SwitchOut)
def apply_dayn_yaml(serial_number: str = Form(...), template_name: str = Form(...), db: Session = Depends(get_db)):
    """
    Aplica Day N:
    - Gates: reachable=True AND state='compliant' AND mgmt_ip existe
    - Render con YAML por serial
    - Guarda render en /data/configs/final (auditoría)
    - Push por SSH
    """
    _ensure_dirs()
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not sw.reachable:
        raise HTTPException(status_code=409, detail="Switch is not reachable (reachable=false)")
    if sw.state != "compliant":
        raise HTTPException(status_code=409, detail=f"Switch state must be 'compliant' (current={sw.state})")
    if not sw.mgmt_ip:
        raise HTTPException(status_code=409, detail="Switch has no mgmt_ip set")

    try:
        vars_data = _read_yaml_vars_for_serial(serial)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML vars: {e}")

    context = {
        "serial_number": sw.serial_number,
        "model": sw.model,
        "family": getattr(sw, "family", None),
        "mgmt_ip": sw.mgmt_ip,
        **vars_data,
    }

    try:
        rendered = _render_template(template_name, context)
    except Exception as e:
        _log(db, serial, f"dayn-render-failed template={template_name} err={e}")
        raise HTTPException(status_code=400, detail=f"Template render failed: {e}")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_name = f"{serial}_dayN_{ts}.cfg"
    out_path = os.path.join(DAYN_DIR, out_name)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rendered.strip() + "\n")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store rendered Day N config: {e}")

    try:
        _push_config_via_ssh(sw.mgmt_ip, out_path)
    except Exception as e:
        _log(db, serial, f"dayn-push-failed ip={sw.mgmt_ip} file={out_name} err={e}")
        raise HTTPException(status_code=502, detail=f"SSH push failed: {e}")

    sw.state = "dayn-applied"
    db.commit()
    db.refresh(sw)
    _log(db, serial, f"dayn-applied-yaml template={template_name} ip={sw.mgmt_ip} file={out_name}")
    return sw
