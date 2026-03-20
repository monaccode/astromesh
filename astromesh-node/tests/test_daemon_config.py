"""Tests for daemon config loading and path detection."""

from unittest.mock import patch

from astromesh_node.daemon.config import DaemonConfig, detect_config_dir


def test_daemon_config_defaults():
    cfg = DaemonConfig()
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8000
    assert cfg.log_level == "info"


def test_daemon_config_from_dict():
    data = {
        "spec": {
            "api": {"host": "127.0.0.1", "port": 9000},
            "services": {"api": True, "agents": True},
            "peers": [{"name": "node2"}],
            "mesh": {"enabled": True},
        }
    }
    cfg = DaemonConfig.from_dict(data)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9000
    assert cfg.services == {"api": True, "agents": True}


def test_detect_config_dir_explicit():
    assert detect_config_dir("/custom/path") == "/custom/path"


def test_detect_config_dir_dev_mode(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "runtime.yaml").write_text("spec: {}")
    with patch("astromesh_node.daemon.config.Path.cwd", return_value=tmp_path):
        result = detect_config_dir(None)
        assert result == str(config_dir)
