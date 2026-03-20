"""Daemon configuration loading and path detection."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from astromesh_node.installer.detect import get_installer


def _system_config_dir() -> str:
    """Return the system config dir for the current platform."""
    try:
        installer = get_installer()
        return str(installer.config_dir())
    except Exception:
        return "/etc/astromesh"


@dataclass
class DaemonConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    services: dict[str, bool] = field(default_factory=dict)
    peers: list[dict] = field(default_factory=list)
    mesh: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> DaemonConfig:
        """Create config from parsed YAML dict."""
        spec = data.get("spec", {})
        api = spec.get("api", {})
        return cls(
            host=api.get("host", "0.0.0.0"),
            port=api.get("port", 8000),
            services=spec.get("services", {}),
            peers=spec.get("peers", []),
            mesh=spec.get("mesh", {}),
        )

    @classmethod
    def from_config_dir(cls, config_dir: str) -> DaemonConfig:
        """Load config from a directory containing runtime.yaml."""
        runtime_path = Path(config_dir) / "runtime.yaml"
        if not runtime_path.exists():
            return cls()
        data = yaml.safe_load(runtime_path.read_text()) or {}
        return cls.from_dict(data)


def detect_config_dir(explicit: str | None) -> str:
    """Auto-detect the config directory.

    Priority: explicit arg > system config > local ./config/ > system default.
    """
    if explicit:
        return explicit

    system_dir = _system_config_dir()
    if os.path.exists(os.path.join(system_dir, "runtime.yaml")):
        return system_dir

    local_config = Path.cwd() / "config"
    if (local_config / "runtime.yaml").exists():
        return str(local_config)

    return system_dir
