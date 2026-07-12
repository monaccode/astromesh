"""Thin, mockable wrapper over huggingface_hub Inference Endpoint APIs.

This is the ONLY module that touches HF over the network. huggingface_hub is imported
lazily inside each function so importing this module (and the provider that falls back to
it) never requires the package at import time. Tests monkeypatch huggingface_hub.

Note: the field mapping in _normalize() reflects the InferenceEndpoint `.raw` payload
(model.revision, compute.accelerator/instanceType/instanceSize) and should be verified
against the live API when the first real endpoint is created.
"""

from __future__ import annotations

from typing import Any

from astromesh.centinela.endpoints import DesiredEndpoint


def _normalize(ep: Any) -> dict:
    raw = getattr(ep, "raw", None) or {}
    compute = raw.get("compute") or {}
    model = raw.get("model") or {}
    return {
        "name": getattr(ep, "name", None),
        "repository": getattr(ep, "repository", None),
        "revision": model.get("revision"),
        "accelerator": compute.get("accelerator"),
        "instance_type": compute.get("instanceType"),
        "instance_size": compute.get("instanceSize"),
        "status": getattr(ep, "status", None),
        "url": getattr(ep, "url", None),
    }


def get_endpoint(name: str, *, namespace: str | None, token: str | None) -> dict | None:
    """Return normalized live state for an endpoint, or None if it does not exist."""
    from huggingface_hub import get_inference_endpoint
    from huggingface_hub.utils import HfHubHTTPError

    try:
        ep = get_inference_endpoint(name, namespace=namespace, token=token)
    except HfHubHTTPError as exc:
        resp = getattr(exc, "response", None)
        if resp is not None and resp.status_code == 404:
            return None
        raise
    return _normalize(ep)


def create_endpoint(desired: DesiredEndpoint, *, namespace: str | None, token: str | None):
    """Create the endpoint described by `desired`."""
    from huggingface_hub import create_inference_endpoint

    return create_inference_endpoint(
        desired.name,
        repository=desired.repository,
        revision=desired.revision,
        framework=desired.framework,
        task=desired.task,
        accelerator=desired.accelerator,
        vendor=desired.vendor,
        region=desired.region,
        type=desired.type,
        instance_size=desired.instance_size,
        instance_type=desired.instance_type,
        namespace=namespace,
        token=token,
        min_replica=desired.min_replica,
        max_replica=desired.max_replica,
        scale_to_zero_timeout=900 if desired.scale_to_zero else None,
    )


def update_endpoint(name: str, fields: dict, *, namespace: str | None, token: str | None):
    """Update an existing endpoint's revision and/or hardware in place."""
    from huggingface_hub import get_inference_endpoint

    ep = get_inference_endpoint(name, namespace=namespace, token=token)
    return ep.update(**fields)


def wait_url(endpoint: Any, *, timeout: int) -> str:
    """Block until the endpoint is running and return its URL."""
    return endpoint.wait(timeout=timeout).url


def resolve_url(name: str, *, namespace: str | None, token: str | None) -> str | None:
    """Best-effort resolve a live URL from an endpoint name (provider fallback)."""
    from huggingface_hub import get_inference_endpoint
    from huggingface_hub.utils import HfHubHTTPError

    try:
        return get_inference_endpoint(name, namespace=namespace, token=token).url
    except HfHubHTTPError:
        return None
