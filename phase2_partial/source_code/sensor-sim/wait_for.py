import os
import socket
import time
import sys
from enroll import enroll_and_authenticate

DEPS = [
    ("mosquitto", os.environ.get("MQTT_HOST", "mosquitto"), int(os.environ.get("MQTT_PORT", "8883"))),
    ("api", os.environ.get("API_HOST", "api"), int(os.environ.get("API_PORT", "8000"))),
]

TIMEOUT = int(os.environ.get("WAIT_TIMEOUT", "120"))
INTERVAL = int(os.environ.get("WAIT_INTERVAL", "2"))


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def main():
    deadline = time.time() + TIMEOUT
    pending_names = []

    while time.time() < deadline:
        pending_names = [name for name, h, p in DEPS if not reachable(h, p)]

        if not pending_names:
            print("[wait] all dependencies reachable")
            break

        print(f"[wait] waiting on: {', '.join(pending_names)}")
        time.sleep(INTERVAL)
    else:
        print(f"[wait] TIMEOUT — still down: {pending_names}")
        sys.exit(1)

    enroll_and_authenticate()

    os.execvp("python", ["python", "-u", "sensor_sim.py"])


if __name__ == "__main__":
    main()