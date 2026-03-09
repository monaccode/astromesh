"""HTTP client for communicating with astromeshd."""

import os

import httpx

DEFAULT_URL = "http://localhost:8000"


def get_base_url() -> str:
    return os.environ.get("ASTROMESH_DAEMON_URL", DEFAULT_URL)


def api_get(path: str) -> dict:
    url = f"{get_base_url()}{path}"
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    return resp.json()
