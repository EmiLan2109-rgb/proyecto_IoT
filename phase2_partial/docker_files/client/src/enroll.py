import os
import json
import time
import requests

API_URL = os.environ.get("API_URL", "http://api:8000")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "node-01")
DEVICE_TYPE = os.environ.get("DEVICE_TYPE", "sensor")
CREDENTIALS_PATH = os.environ.get("DEVICE_CREDENTIALS_PATH", "/app/data/device_credentials.json")


def _load_credentials():
    if os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, "r") as f:
            return json.load(f)
    return None


def _save_credentials(creds: dict):
    os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(creds, f)


def _enroll() -> dict:
    resp = requests.post(
        f"{API_URL}/api/v1/devices",
        json={"device_name": DEVICE_NAME, "device_type": DEVICE_TYPE},
        timeout=10,
    )
    resp.raise_for_status()
    creds = resp.json()  # {"device_id": ..., "api_key": ...}
    print(f"[enroll] node enrolled with device_id={creds['device_id']}")
    return creds


def _authenticate(creds: dict) -> bool:
    resp = requests.get(
        f"{API_URL}/api/v1/devices/me",
        headers={
            "X-Device-Id": creds["device_id"],
            "X-API-Key": creds["api_key"],
        },
        timeout=10,
    )
    if resp.status_code == 200:
        print(f"[auth] node authenticated successfully: {resp.json()}")
        return True
    print(f"[auth] authentication failed ({resp.status_code}): {resp.text}")
    return False


def enroll_and_authenticate(retries: int = 10, delay: int = 3) -> dict:
    """
    Garantiza que el nodo tenga credenciales (enrolando si es la primera vez)
    y confirma que puede autenticarse contra la API antes de continuar.
    """
    creds = _load_credentials()

    for attempt in range(1, retries + 1):
        try:
            if creds is None:
                creds = _enroll()
                _save_credentials(creds)

            if _authenticate(creds):
                return creds

        except requests.exceptions.RequestException as e:
            print(f"[enroll] API not reachable yet ({e}), retry {attempt}/{retries}")

        time.sleep(delay)

    raise RuntimeError("could not enroll/authenticate node against the API")


if __name__ == "__main__":
    enroll_and_authenticate()
