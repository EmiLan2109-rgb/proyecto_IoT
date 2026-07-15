import secrets
import bcrypt
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from auth import verify_device

from db import init_db, get_conn, put_conn

app = FastAPI(title="Device Enrollment API", version="0.1.0")


class DeviceEnrollRequest(BaseModel):
    device_name: str
    device_type: str  # e.g. "sensor", "actuador", "cerradura"


class DeviceEnrollResponse(BaseModel):
    device_id: str
    api_key: str  # se devuelve UNA sola vez, en texto plano


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/api/v1/devices", response_model=DeviceEnrollResponse, status_code=201)
def enroll_device(payload: DeviceEnrollRequest):
    """
    Enrola un nuevo nodo IoT y emite un API Key único.
    El API Key solo se devuelve en esta respuesta; en la base de datos
    únicamente se almacena su hash (bcrypt).
    """
    raw_key = secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO devices (device_name, device_type, api_key_hash)
                VALUES (%s, %s, %s)
                RETURNING device_id
                """,
                (payload.device_name, payload.device_type, key_hash),
            )
            device_id = cur.fetchone()[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db error: {e}")
    finally:
        put_conn(conn)

    return DeviceEnrollResponse(device_id=str(device_id), api_key=raw_key)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}

@app.get("/api/v1/devices/me")
def whoami(device: dict = Depends(verify_device)):
    """
    Endpoint protegido: el nodo se autentica con los headers
    X-Device-Id y X-API-Key. Sirve para comprobar que un nodo
    enrolado puede autenticarse correctamente.
    """
    return {"authenticated": True, **device}
