"""Tests for ServiceManagerProtocol."""

from astromesh_node.platform.base import ServiceManagerProtocol, UnsupportedPlatformError


def test_protocol_is_runtime_checkable():
    assert hasattr(ServiceManagerProtocol, "__protocol_attrs__") or hasattr(
        ServiceManagerProtocol, "__abstractmethods__"
    )


def test_unsupported_platform_error_is_exception():
    err = UnsupportedPlatformError("freebsd")
    assert isinstance(err, Exception)
    assert "freebsd" in str(err)
