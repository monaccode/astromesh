"""Load ProviderConfig documents into a registry and resolve providerRef blocks.

The runtime engine reads config/providers*.yaml at startup into a name->entry registry.
An agent model block { providerRef: <entry_name> } then inherits source/endpoint/contract/
auth from the referenced entry, so a provisioned Centinela endpoint (or any ProviderConfig
entry) is reachable without hand-copying config into the agent spec.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_UNRESOLVED_SOURCE = "__unresolved_provider_ref__"


def load_provider_registry(config_dir) -> dict[str, dict]:
    """Merge every config/providers*.yaml ProviderConfig into one {entry_name: entry} dict."""
    registry: dict[str, dict] = {}
    for path in sorted(Path(config_dir).glob("providers*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError):
            logger.warning("provider registry: could not parse %s; skipping", path)
            continue
        if not isinstance(doc, dict):
            logger.warning("provider registry: %s is not a mapping; skipping", path)
            continue
        providers = (doc.get("spec") or {}).get("providers") or {}
        if not isinstance(providers, dict):
            logger.warning("provider registry: %s has no spec.providers mapping; skipping", path)
            continue
        for name, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            if name in registry:
                logger.warning(
                    "provider registry: entry %r in %s overrides an earlier definition", name, path)
            registry[name] = entry
    return registry


def resolve_block(block: dict, registry: dict) -> dict:
    """Resolve a providerRef block against the registry; blocks without providerRef pass through.

    The referenced entry supplies source (its `type`) + endpoint/endpoint_name/api_key/api_key_env/
    contract/model; the agent block's own non-None keys override. An unresolved providerRef yields a
    block whose source build_candidate_provider maps to None (warn + skip in the engine loop).
    """
    ref = block.get("providerRef")
    if not ref:
        return block

    entry = registry.get(ref)
    if entry is None or not entry.get("type"):
        logger.warning(
            "provider registry: providerRef %r unresolved or has no type; candidate will be "
            "skipped", ref)
        return {"source": _UNRESOLVED_SOURCE, "providerRef": ref}

    models = entry.get("models") or []
    base = {
        "source": entry.get("type"),
        "model": models[0] if models else ref,
        "endpoint": entry.get("endpoint"),
        "endpoint_name": entry.get("endpoint_name"),
        "api_key": entry.get("api_key"),
        "api_key_env": entry.get("api_key_env"),
        "contract": entry.get("contract"),
    }
    overlay = {k: v for k, v in block.items() if k != "providerRef" and v is not None}
    base.update(overlay)
    return base
