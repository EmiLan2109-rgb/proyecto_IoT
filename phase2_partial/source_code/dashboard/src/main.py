import os
from typing import List

import psycopg2
from psycopg2 import sql, pool
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# --- Config desde variables de entorno (mismas que el cliente) ---
PG_HOST = os.environ["POSTGRES_HOST"]
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_DB = os.environ["POSTGRES_DB"]
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]

db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD,
    sslmode="require",
)

app = FastAPI(title="IoT Dashboard API")

# Permitir que el frontend estático consuma la API sin problemas de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn():
    return db_pool.getconn()


def put_conn(conn):
    db_pool.putconn(conn)


def fetch_valid_tables() -> List[str]:
    """Tablas creadas por el cliente MQTT (excluye tablas internas de Postgres)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        put_conn(conn)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/tables")
def list_tables():
    return {"tables": fetch_valid_tables()}


@app.get("/api/data/{table}")
def get_data(table: str, limit: int = 100):
    valid_tables = fetch_valid_tables()
    if table not in valid_tables:
        raise HTTPException(status_code=404, detail=f"Tabla '{table}' no encontrada")

    limit = max(1, min(limit, 1000))  # cota de seguridad

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if table == "devices":
                query = sql.SQL(
                    """
                    SELECT device_id, device_name, device_type, status, created_at, last_seen
                    FROM {table}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """
                ).format(table=sql.Identifier(table))
                cur.execute(query, (limit,))
                rows = cur.fetchall()
                readings = [
                    {
                        "device_id": str(r[0]),
                        "device_name": r[1],
                        "device_type": r[2],
                        "status": r[3],
                        "created_at": r[4].isoformat() if r[4] else None,
                        "last_seen": r[5].isoformat() if r[5] else None,
                    }
                    for r in reversed(rows)
                ]
            else:
                query = sql.SQL(
                    """
                    SELECT id, temp, received_at
                    FROM {table}
                    ORDER BY id DESC
                    LIMIT %s
                    """
                ).format(table=sql.Identifier(table))
                cur.execute(query, (limit,))
                rows = cur.fetchall()
                readings = [
                    {"id": r[0], "temp": r[1], "received_at": r[2].isoformat()}
                    for r in reversed(rows)
                ]
        return {"table": table, "count": len(readings), "readings": readings}
    finally:
        put_conn(conn)


# --- Servir el frontend estático ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
