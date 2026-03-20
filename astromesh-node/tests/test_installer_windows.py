"""Tests for WindowsInstaller."""

from pathlib import PurePosixPath, PureWindowsPath
from unittest.mock import patch

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.windows import WindowsInstaller


def test_implements_protocol():
    assert isinstance(WindowsInstaller(), InstallerProtocol)


def test_config_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramData": "C:\\ProgramData"}
        installer = WindowsInstaller()
        result = installer.config_dir()
        # Compare parts to be platform-agnostic (PosixPath on Linux, WindowsPath on Windows)
        assert result.parts[-3:] == ("ProgramData", "Astromesh", "config")


def test_bin_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramFiles": "C:\\Program Files"}
        installer = WindowsInstaller()
        result = installer.bin_dir()
        assert result.parts[-3:] == ("Program Files", "Astromesh", "venv")
