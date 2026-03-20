"""Tests for MacOSInstaller."""

from pathlib import Path

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.macos import MacOSInstaller


def test_implements_protocol():
    assert isinstance(MacOSInstaller(), InstallerProtocol)


def test_config_dir():
    assert MacOSInstaller().config_dir() == Path("/Library/Application Support/Astromesh/config")


def test_data_dir():
    assert MacOSInstaller().data_dir() == Path("/Library/Application Support/Astromesh/data")


def test_log_dir():
    assert MacOSInstaller().log_dir() == Path("/Library/Logs/Astromesh")


def test_bin_dir():
    assert MacOSInstaller().bin_dir() == Path("/usr/local/opt/astromesh/venv")
