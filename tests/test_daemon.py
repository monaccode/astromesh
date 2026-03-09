"""Tests for astromeshd daemon."""

import os
from unittest.mock import patch

from daemon.astromeshd import (
    DaemonConfig,
    detect_config_dir,
    parse_args,
    remove_pid_file,
    write_pid_file,
)


def test_detect_config_dir_dev_mode(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "runtime.yaml").write_text("apiVersion: astromesh/v1")

    with patch("daemon.astromeshd.Path.cwd", return_value=tmp_path):
        result = detect_config_dir(None)
    assert result == str(config_dir)


def test_detect_config_dir_system_mode(tmp_path):
    etc_dir = tmp_path / "etc" / "astromesh"
    etc_dir.mkdir(parents=True)
    (etc_dir / "runtime.yaml").write_text("apiVersion: astromesh/v1")

    with patch("daemon.astromeshd.SYSTEM_CONFIG_DIR", str(etc_dir)):
        result = detect_config_dir(None)
    assert result == str(etc_dir)


def test_detect_config_dir_explicit():
    result = detect_config_dir("/custom/path")
    assert result == "/custom/path"


def test_write_and_remove_pid_file(tmp_path):
    pid_file = tmp_path / "astromeshd.pid"
    write_pid_file(str(pid_file))
    assert pid_file.exists()
    assert pid_file.read_text().strip() == str(os.getpid())

    remove_pid_file(str(pid_file))
    assert not pid_file.exists()


def test_daemon_config_from_yaml(tmp_path):
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "127.0.0.1"
    port: 9000
""")
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.host == "127.0.0.1"
    assert config.port == 9000


def test_daemon_config_defaults(tmp_path):
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.host == "0.0.0.0"
    assert config.port == 8000


def test_parse_args_defaults():
    args = parse_args([])
    assert args.config is None
    assert args.port is None
    assert args.host is None
    assert args.log_level == "info"


def test_parse_args_custom():
    args = parse_args(["--config", "/etc/astromesh", "--port", "9000", "--log-level", "debug"])
    assert args.config == "/etc/astromesh"
    assert args.port == 9000
    assert args.log_level == "debug"


def test_daemon_config_parses_services(tmp_path):
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  services:
    agents: true
    inference: false
    channels: false
""")
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.services == {"agents": True, "inference": False, "channels": False}


def test_daemon_config_parses_peers(tmp_path):
    runtime_yaml = tmp_path / "runtime.yaml"
    runtime_yaml.write_text("""
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default
spec:
  api:
    host: "0.0.0.0"
    port: 8000
  peers:
    - name: inference-1
      url: http://inference:8000
      services: [inference]
""")
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert len(config.peers) == 1
    assert config.peers[0]["name"] == "inference-1"


def test_daemon_config_defaults_services_and_peers(tmp_path):
    config = DaemonConfig.from_config_dir(str(tmp_path))
    assert config.services == {}
    assert config.peers == []
