import os
import json
import requests
import psycopg2
from psycopg2 import pool, sql
import paho.mqtt.client as mqtt

# --- Config from env ---
MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ["MQTT_PORT"])
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]
MQTT_TOPIC = os.environ["MQTT_TOPIC"]
MQTT_TLS = os.environ.get("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "/app/ca.crt")

API_URL = os.environ.get("API_URL", "http://api:8000")

PG_HOST = os.environ["POSTGRES_HOST"]
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
PG_DB = os.environ["POSTGRES_DB"]
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]

# --- Connection pool (creado una sola vez) ---
db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASSWORD,
    sslmode="require",
)


def table_name_for_metric(metric_name: str) -> str:
    return metric_name.strip("/").replace("/", "_").replace("-", "_")


def ensure_table(cur, table: str):
    query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            id SERIAL PRIMARY KEY,
            device_id UUID NOT NULL,
            room_name TEXT,
            value DOUBLE PRECISION,
            received_at TIMESTAMPTZ DEFAULT NOW()
        )
    """).format(table=sql.Identifier(table))
    cur.execute(query)


def insert_reading(cur, table: str, device_id: str, room_name: str, value):
    query = sql.SQL(
        "INSERT INTO {table} (device_id, room_name, value) VALUES (%s, %s, %s)"
    ).format(table=sql.Identifier(table))
    cur.execute(query, (device_id, room_name, value))


def verify_device(device_id: str, api_key: str) -> dict | None:
    """
    Valida el dispositivo contra la API antes de confiar en el dato.
    Devuelve el dict con device_name/device_type/room_name si es válido,
    o None si la autenticación falla.
    """
    try:
        resp = requests.post(
            f"{API_URL}/api/v1/devices/verify",
            json={"device_id": device_id, "api_key": api_key},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"[auth] rejected device_id={device_id}: {resp.status_code} {resp.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[auth] API not reachable, discarding message: {e}")
        return None


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[mqtt] connected rc={rc}, subscribing to {MQTT_TOPIC}")
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    topic = msg.topic

    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[warn] non-JSON payload on {topic}: {msg.payload!r}")
        return

    device_id = payload.get("device_id")
    api_key = payload.get("api_key")
    metric_name = payload.get("metric_name")
    value = payload.get("value")

    if not device_id or not api_key or not metric_name or value is None:
        print(f"[warn] incomplete payload on {topic}: {payload}")
        return

    device = verify_device(device_id, api_key)
    if device is None:
        print(f"[warn] discarding unauthenticated message from device_id={device_id}")
        return

    room_name = device.get("room_name")
    table = table_name_for_metric(metric_name)

    print(f"[mqtt] {topic} -> device={device_id} room={room_name} {metric_name}={value}")

    conn = None
    try:
        conn = db_pool.getconn()
        conn.autocommit = True
        with conn.cursor() as cur:
            ensure_table(cur, table)
            insert_reading(cur, table, device_id, room_name, value)
        print(f"[db] stored in table '{table}'")
    except Exception as e:
        print(f"[db error] {e}")
    finally:
        if conn is not None:
            db_pool.putconn(conn)


def main():
    client = mqtt.Client(client_id="pg-client", protocol=mqtt.MQTTv5)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    if MQTT_TLS:
        client.tls_set(ca_certs=MQTT_CA_CERT)

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            print(f"[connect error] {e}, retrying in 5s...")
            import time
            time.sleep(5)


if __name__ == "__main__":
    main()