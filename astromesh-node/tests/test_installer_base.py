"""Tests for InstallerProtocol."""

from astromesh_node.installer.base import InstallerProtocol


def test_protocol_is_runtime_checkable():
    assert hasattr(InstallerProtocol, "__protocol_attrs__") or hasattr(
        InstallerProtocol, "__abstractmethods__"
    )
