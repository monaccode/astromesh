"""Tests for daemon core — argument parsing."""

from astromesh_node.daemon.core import parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.config is None
    assert args.host is None
    assert args.port is None
    assert args.log_level == "info"
    assert args.foreground is False


def test_parse_args_foreground():
    args = parse_args(["--foreground"])
    assert args.foreground is True


def test_parse_args_config():
    args = parse_args(["--config", "/etc/astromesh"])
    assert args.config == "/etc/astromesh"
