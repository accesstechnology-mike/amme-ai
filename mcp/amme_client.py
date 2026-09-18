import os
import subprocess
from pathlib import Path

import httpx

BASE_URL = os.environ.get("AMME_API_BASE", "https://api.emma-app.com")

_AUTH_SCRIPT = Path(
    os.environ.get(
        "AMME_AUTH_SCRIPT",
        "../scripts/auth.sh",
    )
)


def _bearer() -> str:
    result = subprocess.run([str(_AUTH_SCRIPT)], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _headers() -> dict:
    return {"Authorization": f"Bearer {_bearer()}"}


def get(path: str, params: dict | None = None) -> dict | list:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        r = c.get(path, headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


def post(path: str, body: dict) -> dict | list:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        r = c.post(path, headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


def patch(path: str, body: list | dict) -> dict | list:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        r = c.patch(path, headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


def delete(path: str) -> dict:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        r = c.delete(path, headers=_headers())
        r.raise_for_status()
        return r.json() if r.content else {"status": "deleted"}
