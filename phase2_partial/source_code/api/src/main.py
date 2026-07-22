import os
import secrets
import bcrypt
from auth import _check_device, DeviceVerifyRequest
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from db import init_db, get_conn, put_conn

ADMIN_KEY = os.environ["ADMIN_KEY"]

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Device Enrollment API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class DeviceEnrollRequest(BaseModel):
    device_name: str
    device_type: str


class DeviceEnrollResponse(BaseModel):
    device_id: str
    api_key: str


class RoomCreate(BaseModel):
    room_name: str
    cidr: str


def verify_admin(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="invalid admin key")


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/api/v1/devices", response_model=DeviceEnrollResponse, status_code=201)
@limiter.limit("5/minute")
def enroll_device(payload: DeviceEnrollRequest, request: Request):
    """
    Enrola un nuevo nodo IoT y emite un API Key único.
    La IP de origen debe pertenecer a una sala (room) registrada.
    """
    client_ip = request.client.host

    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT room_name FROM rooms WHERE %s::inet <<= cidr LIMIT 1",
                (client_ip,),
            )
            room_row = cur.fetchone()

            if room_row is None:
                raise HTTPException(
                    status_code=403,
                    detail=f"IP {client_ip} no pertenece a ninguna sala registrada",
                )
            room_name = room_row[0]

            raw_key = secrets.token_urlsafe(32)
            key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

            cur.execute(
                """
                INSERT INTO devices (device_name, device_type, api_key_hash, room_name, enrolled_ip)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING device_id
                """,
                (payload.device_name, payload.device_type, key_hash, room_name, client_ip),
            )
            device_id = cur.fetchone()[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db error: {e}")
    finally:
        put_conn(conn)

    return DeviceEnrollResponse(device_id=str(device_id), api_key=raw_key)


@app.post("/api/v1/rooms", status_code=201)
@limiter.limit("10/minute")
def create_room(payload: RoomCreate, request: Request, admin=Depends(verify_admin)):
    """
    Registra una subred (habitación) para identificación de dispositivos por IP.
    Protegido con header X-Admin-Key.
    """
    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rooms (room_name, cidr)
                VALUES (%s, %s)
                ON CONFLICT (room_name) DO UPDATE SET cidr = EXCLUDED.cidr
                """,
                (payload.room_name, payload.cidr),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db error: {e}")
    finally:
        put_conn(conn)

    return {"room_name": payload.room_name, "cidr": payload.cidr}


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/devices/me")
@limiter.limit("30/minute")
def whoami(request: Request, x_device_id: str = Header(...), x_api_key: str = Header(...)):
    """
    Endpoint protegido: el nodo se autentica con los headers
    X-Device-Id y X-API-Key.
    """
    device = _check_device(x_device_id, x_api_key)
    return {"authenticated": True, **device}


@app.post("/api/v1/devices/verify")
@limiter.limit("60/minute")
def verify_device_endpoint(payload: DeviceVerifyRequest, request: Request):
    """
    Verifica device_id/api_key enviados por body JSON.
    Usado por client.py para validar mensajes MQTT antes de insertar.
    """
    device = _check_device(payload.device_id, payload.api_key)
    return {"authenticated": True, **device}