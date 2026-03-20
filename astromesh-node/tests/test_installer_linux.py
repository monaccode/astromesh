"""Tests for LinuxInstaller."""

from pathlib import Path

from astromesh_node.installer.base import InstallerProtocol
from astromesh_node.installer.linux import LinuxInstaller


def test_implements_protocol():
    installer = LinuxInstaller()
    assert isinstance(installer, InstallerProtocol)


def test_config_dir():
    assert LinuxInstaller().config_dir() == Path("/etc/astromesh")


def test_data_dir():
    assert LinuxInstaller().data_dir() == Path("/var/lib/astromesh")


def test_log_dir():
    assert LinuxInstaller().log_dir() == Path("/var/log/astromesh")


def test_bin_dir():
    assert LinuxInstaller().bin_dir() == Path("/opt/astromesh/venv")


async def test_verify_returns_list():
    installer = LinuxInstaller()
    problems = await installer.verify()
    assert isinstance(problems, list)
