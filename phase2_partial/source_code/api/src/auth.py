import uuid
import bcrypt
from pydantic import BaseModel
from datetime import datetime, timezone
from fastapi import HTTPException
from db import get_conn, put_conn


class DeviceVerifyRequest(BaseModel):
    device_id: str
    api_key: str


def _check_device(device_id: str, api_key: str) -> dict:
    """
    Lógica compartida de verificación: valida device_id/api_key
    contra la BD y actualiza last_seen si es exitoso.
    """
    try:
        uuid.UUID(device_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=401, detail="invalid device_id format")

    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT device_id, device_name, device_type, api_key_hash, status, room_name "
                "FROM devices WHERE device_id = %s",
                (device_id,),
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=401, detail="device not found")

            d_id, device_name, device_type, api_key_hash, status, room_name = row

            if status != "active":
                raise HTTPException(status_code=403, detail=f"device status: {status}")

            if not bcrypt.checkpw(api_key.encode(), api_key_hash.encode()):
                raise HTTPException(status_code=401, detail="invalid api key")

            cur.execute(
                "UPDATE devices SET last_seen = %s WHERE device_id = %s",
                (datetime.now(timezone.utc), d_id),
            )

            return {
                "device_id": str(d_id),
                "device_name": device_name,
                "device_type": device_type,
                "room_name": room_name,
            }
    finally:
        put_conn(conn)