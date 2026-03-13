from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from models import Base, Switch
from database import get_db
from routers import switches, versions, images
from schemas import SwitchOut
from database import Base, engine

# Crear tablas
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Registrar los routers
app.include_router(switches.router)
app.include_router(versions.router)
app.include_router(images.router)

#change
#@app.get("/")
#def root():
#    return {"msg": "Provisioning API running"}

@app.get("/switches", response_model=list[SwitchOut])
def list_switches(db: Session = Depends(get_db)):
    switches = db.query(Switch).all()
    return switches