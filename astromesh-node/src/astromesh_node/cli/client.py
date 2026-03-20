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


def api_post(path: str, json: dict | None = None) -> dict:
    url = f"{get_base_url()}{path}"
    resp = httpx.post(url, json=json, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def api_post_with_timeout(path: str, json: dict | None = None, timeout: float = 30.0) -> dict:
    """POST with configurable timeout for long-running operations."""
    url = f"{get_base_url()}{path}"
    resp = httpx.post(url, json=json, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def api_get_params(path: str, params: dict | None = None, timeout: float = 5.0) -> dict:
    """GET with query parameters."""
    url = f"{get_base_url()}{path}"
    resp = httpx.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
