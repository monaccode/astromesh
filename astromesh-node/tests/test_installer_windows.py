"""Tests for WindowsInstaller."""

from pathlib import Path
from unittest.mock import patch

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.windows import WindowsInstaller


def test_implements_protocol():
    assert isinstance(WindowsInstaller(), InstallerProtocol)


def test_config_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramData": "C:\\ProgramData"}
        installer = WindowsInstaller()
        assert installer.config_dir() == Path("C:\\ProgramData\\Astromesh\\config")


def test_bin_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramFiles": "C:\\Program Files"}
        installer = WindowsInstaller()
        assert installer.bin_dir() == Path("C:\\Program Files\\Astromesh\\venv")
