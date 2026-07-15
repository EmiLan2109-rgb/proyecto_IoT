import bcrypt
from fastapi import Header, HTTPException
from datetime import datetime, timezone

from db import get_conn, put_conn


def verify_device(x_device_id: str = Header(...), x_api_key: str = Header(...)) -> dict:
    """
    Dependencia de FastAPI que autentica a un nodo usando dos headers:
      X-Device-Id: UUID devuelto en el enrolamiento
      X-API-Key:   API Key en texto plano devuelta en el enrolamiento

    Verifica el hash bcrypt almacenado y que el dispositivo esté 'active'.
    Actualiza last_seen si la autenticación es exitosa.
    """
    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT device_id, device_name, device_type, api_key_hash, status "
                "FROM devices WHERE device_id = %s",
                (x_device_id,),
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=401, detail="device not found")

            device_id, device_name, device_type, api_key_hash, status = row

            if status != "active":
                raise HTTPException(status_code=403, detail=f"device status: {status}")

            if not bcrypt.checkpw(x_api_key.encode(), api_key_hash.encode()):
                raise HTTPException(status_code=401, detail="invalid api key")

            cur.execute(
                "UPDATE devices SET last_seen = %s WHERE device_id = %s",
                (datetime.now(timezone.utc), device_id),
            )

            return {
                "device_id": str(device_id),
                "device_name": device_name,
                "device_type": device_type,
            }
    finally:
        put_conn(conn)
