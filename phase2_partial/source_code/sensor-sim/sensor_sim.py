import os
import json
import time
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ["MQTT_PORT"])
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]
MQTT_TOPIC = os.environ["MQTT_TOPIC"]
MQTT_TLS = os.environ.get("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "/app/ca.crt")

TEMP_MIN = 23.0
TEMP_MAX = 27.0
STEP = 0.2
INTERVAL = 5

def temperature_sequence():
    """Generador infinito: onda triangular entre TEMP_MIN y TEMP_MAX."""
    temp = TEMP_MIN
    direction = 1
    while True:
        yield round(temp, 2)
        temp += direction * STEP
        if temp >= TEMP_MAX:
            temp = TEMP_MAX
            direction = -1
        elif temp <= TEMP_MIN:
            temp = TEMP_MIN
            direction = 1


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[sensor-sim] connected rc={rc}, publishing to {MQTT_TOPIC}")


def main():
    client = mqtt.Client(client_id="sensor-sim", protocol=mqtt.MQTTv5)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect

    if MQTT_TLS:
        client.tls_set(ca_certs=MQTT_CA_CERT)

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            break
        except Exception as e:
            print(f"[sensor-sim] connect error: {e}, retrying in 5s...")
            time.sleep(5)

    for temp in temperature_sequence():
        payload = json.dumps({"temp": temp})
        client.publish(MQTT_TOPIC, payload)
        print(f"[sensor-sim] published -> {payload}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
