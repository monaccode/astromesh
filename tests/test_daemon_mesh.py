"""Tests for daemon mesh wiring."""

import pytest
import yaml

from daemon.astromeshd import DaemonConfig


def test_daemon_config_parses_mesh(tmp_path):
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text(yaml.dump({
        "apiVersion": "astromesh/v1",
        "kind": "RuntimeConfig",
        "metadata": {"name": "test"},
        "spec": {
            "api": {"host": "0.0.0.0", "port": 8000},
            "mesh": {
                "enabled": True,
                "node_name": "worker-1",
                "seeds": ["http://gateway:8000"],
                "heartbeat_interval": 10,
            },
        },
    }))
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.mesh["enabled"] is True
    assert config.mesh["node_name"] == "worker-1"
    assert config.mesh["seeds"] == ["http://gateway:8000"]


def test_daemon_config_no_mesh(tmp_path):
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text(yaml.dump({
        "apiVersion": "astromesh/v1",
        "kind": "RuntimeConfig",
        "metadata": {"name": "test"},
        "spec": {"api": {"host": "0.0.0.0", "port": 8000}},
    }))
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.mesh == {}


def test_daemon_config_mesh_disabled(tmp_path):
    runtime = tmp_path / "runtime.yaml"
    runtime.write_text(yaml.dump({
        "apiVersion": "astromesh/v1",
        "kind": "RuntimeConfig",
        "metadata": {"name": "test"},
        "spec": {
            "api": {"host": "0.0.0.0", "port": 8000},
            "mesh": {"enabled": False},
        },
    }))
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.mesh["enabled"] is False
