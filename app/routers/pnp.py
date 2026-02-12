from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import xml.etree.ElementTree as ET
import time
from services.parser import extract_serial

from services.ssh_client import get_switch_info
from services.parser import parse_show_version

router = APIRouter(prefix="/pnp", tags=["PnP"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/")
async def pnp_callback(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    xml_data = body.decode()

    # IP real del switch que envió el XML PnP
    switch_ip = request.client.host
    switch_port = 2222

    serial = extract_serial(xml_data)
    if not serial:
        return {"error": "No serial found in XML"}
    
    # Intentos de SSH
    max_retries = 10
    wait_time = 3

    raw_output = None

    for attempt in range(max_retries):
        try:
            print(f"[SSH] Intento {attempt+1}/{max_retries} hacia {switch_ip}:{switch_port}...")
            raw_output = get_switch_info(
                host=switch_ip,
                port=switch_port,
                username="carlovalle",
                password="M@iden10291990"
            )
            break
        except Exception as e:
            print(f"[SSH] Falló intento {attempt+1}: {e}")
            time.sleep(wait_time)

    if not raw_output:
        return {"error": f"Switch {switch_ip} no respondió por SSH"}

    model, version = parse_show_version(raw_output)

    sw = db.query(models.Switch).filter(models.Switch.serial_number == serial).first()
    if sw:
        sw.model = model
        sw.current_version = version
        sw.state = "staging"

        db.add(
            models.ProvisioningLog(
                serial_number=serial,
                event="SSH information collected"
            )
        )
        db.commit()

    return {
        "message": "PnP complete + SSH OK",
        "switch_ip": switch_ip,
        "model": model,
        "version": version
    }
