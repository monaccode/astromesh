"""Tests for WindowsInstaller."""

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
        # On Linux, backslashes in "C:\ProgramData" are NOT path separators,
        # so Path treats it as a single component. Compare last 2 parts only.
        assert result.parts[-2:] == ("Astromesh", "config")
        assert "ProgramData" in str(result)


def test_bin_dir():
    with patch("astromesh_node.installer.windows.os") as mock_os:
        mock_os.environ = {"ProgramFiles": "C:\\Program Files"}
        installer = WindowsInstaller()
        result = installer.bin_dir()
        assert result.parts[-2:] == ("Astromesh", "venv")
        assert "Program Files" in str(result)
