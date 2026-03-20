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

IMAGE_REPO_BASE_URL = os.getenv("IMAGE_REPO_BASE_URL", "http://10.1.12.89:8081")


def _ensure_dirs() -> None:
    os.makedirs(DAY0_DIR, exist_ok=True)
    os.makedirs(DAYN_DIR, exist_ok=True)
    os.makedirs(DAYN_TEMPLATES_DIR, exist_ok=True)
    os.makedirs(DAYN_VARS_DIR, exist_ok=True)


def _log(db: Session, serial: str, event: str) -> None:
    db.add(
        models.ProvisioningLog(
            serial_number=serial,
            event=event,
            timestamp=datetime.utcnow(),
        )
    )


def _tcp_check(host: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def _push_nac_config_via_ssh(host: str, config_path: str) -> None:
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
        "session_log": "/data/dayn_nac_netmiko.log",
    }

    conn = ConnectHandler(**device)
    try:
        if SWITCH_SSH_SECRET:
            conn.enable()

        conn.config_mode()

        with open(config_path, "r", encoding="utf-8") as f:
            commands = [line.rstrip() for line in f if line.strip()]

        for cmd in commands:
            output = conn.send_command_timing(cmd, strip_prompt=False, strip_command=False)

            if "Do you wish to continue? [yes]:" in output:
                output += conn.send_command_timing("yes", strip_prompt=False, strip_command=False)

            if "% Invalid input" in output or "% Incomplete command" in output or "% Ambiguous command" in output:
                print(f"[NAC PUSH] skipping unsupported command: {cmd}")
                continue

        conn.exit_config_mode()
        conn.save_config()

    finally:
        try:
            conn.disconnect()
        except Exception:
            pass

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
        "session_log": "/tmp/dayn_netmiko.log",
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

def _render_day0_template(template_name: str, context: dict) -> str:
    day0_templates_dir = os.getenv("DAY0_TEMPLATES_DIR", "/Open_PnP_Server/configs/templates")

    env = Environment(
        loader=FileSystemLoader(day0_templates_dir),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template(template_name)
    return tpl.render(**context)

def normalize_version(version: Optional[str]) -> Optional[str]:
    if not version:
        return version

    parts = version.strip().split(".")
    normalized = []

    for p in parts:
        if p.isdigit():
            normalized.append(str(int(p)))
        else:
            normalized.append(p)

    return ".".join(normalized)


def _render_template(template_name: str, context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(DAYN_TEMPLATES_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template(template_name)
    return tpl.render(**context)


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
        brand=None,
        role=None,
        current_version=None,
        recommended_version=None,
        state="non-connected",
        mgmt_ip=None,
        last_seen_ip=None,
        reachable=False,
    )

    db.add(sw)
    _log(db, serial, "registered")
    db.commit()
    db.refresh(sw)
    return sw


@router.post("/report-ip", response_model=schemas.SwitchOut)
def report_ip(payload: schemas.ReportIP, db: Session = Depends(get_db)):
    serial = payload.serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.last_seen_ip = payload.last_seen_ip.strip()

    if not sw.mgmt_ip:
        sw.mgmt_ip = sw.last_seen_ip

    if payload.mgmt_ip:
        sw.mgmt_ip = payload.mgmt_ip.strip()

    _log(db, serial, f"reported-ip last_seen={sw.last_seen_ip} mgmt={sw.mgmt_ip}")
    db.commit()
    db.refresh(sw)
    return sw

@router.post("/apply-dayn-base")
def apply_dayn_base(serial_number: str):

    template_name = "template_access_base.j2"

    cfg_path = render_dayn_yaml(serial_number, template_name)

    sw = get_switch(serial_number)

    if not sw.mgmt_ip:
        raise HTTPException(400, "Switch has no mgmt_ip")

    _push_config_via_ssh(sw.mgmt_ip, cfg_path)

    update_state(serial_number, "dayn-base-applied")

    return {"status": "ok", "stage": "base"}

@router.post("/apply-dayn-nac")
def apply_dayn_nac(serial_number: str):

    template_name = "template_access_nac.j2"

    cfg_path = render_dayn_yaml(serial_number, template_name)

    sw = get_switch(serial_number)

    _push_config_via_ssh(sw.mgmt_ip, cfg_path)

    update_state(serial_number, "dayn-nac-applied")

    return {"status": "ok", "stage": "nac"}

@router.post("/apply-dayn-aaa-final")
def apply_dayn_aaa(serial_number: str):

    template_name = "template_access_aaa_final.j2"

    cfg_path = render_dayn_yaml(serial_number, template_name)

    sw = get_switch(serial_number)

    _push_config_via_ssh(sw.mgmt_ip, cfg_path)

    update_state(serial_number, "dayn-complete")

    return {"status": "ok", "stage": "aaa"}

@router.post("/set-mgmt-ip", response_model=schemas.SwitchOut)
def set_mgmt_ip(serial_number: str = Form(...), mgmt_ip: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.mgmt_ip = mgmt_ip.strip()
    _log(db, serial, f"set-mgmt-ip mgmt={sw.mgmt_ip}")
    db.commit()
    db.refresh(sw)
    return sw

@router.post("/check-reachable", response_model=schemas.SwitchOut)
def check_reachable(serial_number: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    candidate_ips = []

    if sw.mgmt_ip and sw.mgmt_ip.strip():
        candidate_ips.append(sw.mgmt_ip)

    if sw.last_seen_ip and sw.last_seen_ip.strip():
        if sw.last_seen_ip not in candidate_ips:
            candidate_ips.append(sw.last_seen_ip)

    # Si no hay IPs para probar
    if not candidate_ips:
        sw.reachable = False
        sw.last_reachability_check = datetime.utcnow()

        _log(db, serial, "reachability-check no candidate IPs")

        db.commit()
        db.refresh(sw)
        return sw

    reachable_ip = None

    for ip in candidate_ips:
        if _tcp_check(ip, port=22, timeout=2.0):
            reachable_ip = ip
            break

    sw.reachable = reachable_ip is not None

    # sincronizar mgmt_ip si last_seen_ip fue la alcanzable
    if reachable_ip and reachable_ip == sw.last_seen_ip and sw.mgmt_ip != sw.last_seen_ip:
        sw.mgmt_ip = sw.last_seen_ip

    sw.last_reachability_check = datetime.utcnow()

    _log(
        db,
        serial,
        f"reachability-check candidates={candidate_ips} reachable={sw.reachable} via={reachable_ip}",
    )

    db.commit()
    db.refresh(sw)

    return sw

@router.post("/report-version", response_model=schemas.SwitchOut)
def report_version(payload: schemas.ReportVersion, db: Session = Depends(get_db)):
    serial = payload.serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.current_version = normalize_version(payload.current_version)

    if payload.model is not None:
        sw.model = payload.model.strip() if payload.model else None

    fam: Optional[str] = detect_family(sw.model) if sw.model else None
    sw.family = fam

    rec = None
    matching_row = None

    if fam:
        rec_rows = (
            db.query(models.RecommendedVersion)
            .filter(models.RecommendedVersion.family == fam)
            .all()
        )

        recommended_rows = [r for r in rec_rows if getattr(r, "is_recommended", False)]
        if recommended_rows:
            recommended_rows.sort(key=lambda x: x.id, reverse=True)
            rec = normalize_version(recommended_rows[0].version)

        current_norm = normalize_version(sw.current_version)
        for row in rec_rows:
            if normalize_version(row.version) == current_norm:
                matching_row = row
                break

    sw.recommended_version = rec

    if sw.current_version:
        if matching_row and getattr(matching_row, "is_recommended", False):
            sw.state = "compliant"
        else:
            sw.state = "non-compliant"
    else:
        sw.state = "staging"

    _log(
        db,
        serial,
        f"reported-version model={sw.model} current={sw.current_version} "
        f"family={fam} recommended={sw.recommended_version} state={sw.state}",
    )
    db.commit()
    db.refresh(sw)
    return sw
@router.post("/set-metadata", response_model=schemas.SwitchOut)
def set_metadata(
    serial_number: str = Form(...),
    brand: str | None = Form(None),
    role: str | None = Form(None),
    db: Session = Depends(get_db),
):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if brand is not None:
        sw.brand = brand.strip() or None

    if role is not None:
        sw.role = role.strip() or None

    _log(db, serial, f"metadata-updated brand={sw.brand} role={sw.role}")
    db.commit()
    db.refresh(sw)
    return sw

@router.post("/set-state", response_model=schemas.SwitchOut)
def set_state(
    serial_number: str = Form(...),
    state: str = Form(...),
    db: Session = Depends(get_db),
):
    serial = serial_number.strip()
    new_state = state.strip()

    allowed = {
        "non-connected",
        "configured",
        "staging",
        "non-compliant",
        "upgrade-planned",
        "upgrading",
        "upgrade-complete",
        "upgrade-failed",
        "compliant",
        "dayn-applied",
    }

    if new_state not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid state: {new_state}")

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.state = new_state
    _log(db, serial, f"state-changed {new_state}")
    db.commit()
    db.refresh(sw)
    return sw


@router.post("/config-applied", response_model=schemas.SwitchOut)
def config_applied(serial_number: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    sw.state = "configured"
    _log(db, serial, "config-applied")
    db.commit()
    db.refresh(sw)
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
    _log(db, serial, f"day0-uploaded path={day0_path}")
    db.commit()
    db.refresh(sw)
    return sw


@router.get("/ips/{serial_number}")
def get_switch_ips(serial_number: str, db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    return {
        "mgmt_ip": sw.mgmt_ip,
        "last_seen_ip": sw.last_seen_ip,
        "reachable": sw.reachable,
    }


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
    allowed_states = {
        "compliant",
        "dayn-base-applied",
        "dayn-nac-applied",
        "dayn-applied",
    }
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not sw.reachable:
        raise HTTPException(status_code=409, detail="Switch is not reachable (reachable=false)")
    if sw.state not in allowed_states:
        raise HTTPException(
            status_code=409,
            detail=f"Switch state must be one of {sorted(allowed_states)} (current={sw.state})"
        )
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
        db.commit()
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
        if template_name == "template_access_nac.j2":
            _push_nac_config_via_ssh(sw.mgmt_ip, out_path)
        else:
            _push_config_via_ssh(sw.mgmt_ip, out_path)
    except Exception as e:
        _log(db, serial, f"dayn-push-failed ip={sw.mgmt_ip} file={out_name} err={e}")
        db.commit()
        raise HTTPException(status_code=502, detail=f"SSH push failed: {e}")

    #sw.state = "dayn-applied"
    if template_name == "template_access_base.j2":
        sw.state = "dayn-base-applied"
    elif template_name == "template_access_nac.j2":
        sw.state = "dayn-nac-applied"
    elif template_name == "template_access_aaa_final.j2":
        sw.state = "dayn-applied"
    else:
        sw.state = "dayn-applied"
    _log(db, serial, f"dayn-applied-yaml template={template_name} ip={sw.mgmt_ip} file={out_name}")
    db.commit()
    db.refresh(sw)
    return sw


@router.post("/request-upgrade", response_model=schemas.SwitchOut)
def request_upgrade(serial_number: str = Form(...), db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not sw.mgmt_ip:
        raise HTTPException(status_code=409, detail="Switch has no mgmt_ip")
    if not sw.reachable:
        raise HTTPException(status_code=409, detail="Switch is not reachable")
    if not sw.recommended_version:
        raise HTTPException(status_code=409, detail="Switch has no recommended_version")

    sw.state = "upgrade-planned"
    _log(db, serial, "manual-upgrade-requested")
    db.commit()
    db.refresh(sw)
    return sw


@router.post("/upload-dayn-vars", response_model=schemas.SwitchOut)
def upload_dayn_vars(
    serial_number: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Sube archivo YAML de variables DAY-N y lo guarda como:
    /data/vars/dayn/<SERIAL>.yml
    """
    _ensure_dirs()
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    if not file.filename.lower().endswith((".yml", ".yaml")):
        raise HTTPException(status_code=400, detail="Only .yml or .yaml files are allowed")

    vars_path = os.path.join(DAYN_VARS_DIR, f"{serial}.yml")

    try:
        content = file.file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        try:
            parsed = yaml.safe_load(content.decode("utf-8")) or {}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML must be an object (key: value) at top level")

        with open(vars_path, "wb") as f:
            f.write(content)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store DAY-N vars: {e}")
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    _log(db, serial, f"dayn-vars-uploaded path={vars_path}")
    db.commit()
    db.refresh(sw)
    return sw

@router.post("/generate-day0-from-vars", response_model=schemas.SwitchOut)
def generate_day0_from_vars(
    serial_number: str = Form(...),
    file: UploadFile = File(...),
    template_name: str = Form("template.j2"),
    db: Session = Depends(get_db),
):
    """
    Recibe archivo de variables desde GUI/ServiceNow.
    Genera:
      - Day 0 config: /Open_PnP_Server/configs/<SERIAL>.cfg
      - Day N vars:    /data/vars/dayn/<SERIAL>.yml
    """

    _ensure_dirs()
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    try:
        raw_content = file.file.read()
        if not raw_content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        try:
            vars_data = yaml.safe_load(raw_content.decode("utf-8")) or {}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML variables file: {e}")

        if not isinstance(vars_data, dict):
            raise HTTPException(status_code=400, detail="Variables file must be a YAML object")

        # --------
        # Day N .yml
        # --------
        dayn_vars_path = os.path.join(DAYN_VARS_DIR, f"{serial}.yml")
        with open(dayn_vars_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(vars_data, f, sort_keys=False, allow_unicode=True)

        # --------
        # Day 0 .cfg
        # --------
        day0_context = {
            "serial_number": serial,
            **vars_data,
        }

        try:
            rendered_day0 = _render_day0_template(template_name, day0_context)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Day0 template render failed: {e}")

        day0_cfg_path = os.path.join(DAY0_DIR, f"{serial}.cfg")
        with open(day0_cfg_path, "w", encoding="utf-8") as f:
            f.write(rendered_day0.strip() + "\n")

        # Estado sugerido después de generar Day 0
        sw.state = "staging"

        _log(
            db,
            serial,
            f"day0-generated template={template_name} cfg={day0_cfg_path} dayn_vars={dayn_vars_path}",
        )
        db.commit()
        db.refresh(sw)
        return sw

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate Day0/DayN files: {e}")
    finally:
        try:
            file.file.close()
        except Exception:
            pass

@router.delete("/{serial_number}")
def delete_switch(serial_number: str, db: Session = Depends(get_db)):
    serial = serial_number.strip()

    sw = db.query(models.Switch).filter(
        models.Switch.serial_number == serial
    ).first()

    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    # 🧹 opcional: borrar archivos asociados
    try:
        import os

        day0_path = f"/Open_PnP_Server/configs/{serial}.cfg"
        dayn_vars_path = f"/data/vars/dayn/{serial}.yml"

        if os.path.exists(day0_path):
            os.remove(day0_path)

        if os.path.exists(dayn_vars_path):
            os.remove(dayn_vars_path)

    except Exception as e:
        print(f"[delete_switch] warning cleaning files: {e}")

    db.delete(sw)
    db.commit()

    return {"message": f"Switch {serial} deleted successfully"}

@router.get("/{serial_number}/upgrade-plan", response_model=schemas.UpgradePlanOut)
def get_upgrade_plan(serial_number: str, db: Session = Depends(get_db)):
    serial = serial_number.strip()
    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if not sw:
        raise HTTPException(status_code=404, detail=f"Switch {serial} not found")

    if not sw.family:
        raise HTTPException(status_code=409, detail="Switch family is not set")

    if not sw.recommended_version:
        raise HTTPException(status_code=409, detail="Switch has no recommended_version")

    if sw.state not in {"non-compliant", "upgrade-planned"}:
        raise HTTPException(
            status_code=409,
            detail=f"Upgrade plan only available for non-compliant switches (current state={sw.state})",
        )

    image_row = (
        db.query(models.ImageCatalog)
        .filter(models.ImageCatalog.family == sw.family)
        .filter(models.ImageCatalog.version == sw.recommended_version)
        .first()
    )

    if not image_row:
        raise HTTPException(
            status_code=404,
            detail=f"No image found for family={sw.family} version={sw.recommended_version}",
        )

    folder = sw.family.lower()
    image_url = f"{IMAGE_REPO_BASE_URL}/{folder}/{image_row.filename}"

    return schemas.UpgradePlanOut(
        serial_number=sw.serial_number,
        family=sw.family,
        current_version=sw.current_version,
        recommended_version=sw.recommended_version,
        filename=image_row.filename,
        image_url=image_url,
        mgmt_ip=sw.mgmt_ip,
        reachable=sw.reachable,
        state=sw.state,
    )