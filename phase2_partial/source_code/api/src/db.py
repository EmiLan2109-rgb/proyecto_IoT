import os
import psycopg2
from psycopg2 import pool

PG_HOST = os.environ["POSTGRES_HOST"]
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_DB = os.environ["POSTGRES_DB"]
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]

db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD,
)


def get_conn():
    return db_pool.getconn()


def put_conn(conn):
    db_pool.putconn(conn)


def init_db():
    """Crea la tabla devices si no existe (modelo tomado del proposal document)."""
    conn = get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Requerida para gen_random_uuid()
            cur.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ
                )
                """
            )
    finally:
        put_conn(conn)
