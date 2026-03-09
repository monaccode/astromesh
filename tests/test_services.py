"""Tests for ServiceManager."""

from astromesh.runtime.services import DEFAULT_SERVICES, ServiceManager


def test_default_services():
    sm = ServiceManager({})
    for service in DEFAULT_SERVICES:
        assert sm.is_enabled(service) is True


def test_explicit_disable():
    sm = ServiceManager({"inference": False, "channels": False})
    assert sm.is_enabled("inference") is False
    assert sm.is_enabled("channels") is False
    assert sm.is_enabled("agents") is True
    assert sm.is_enabled("api") is True


def test_enabled_services_list():
    sm = ServiceManager({"inference": False, "rag": False})
    enabled = sm.enabled_services()
    assert "inference" not in enabled
    assert "rag" not in enabled
    assert "agents" in enabled
    assert "api" in enabled


def test_unknown_service():
    sm = ServiceManager({})
    assert sm.is_enabled("nonexistent") is False


def test_validate_warns_agents_without_tools():
    sm = ServiceManager({"agents": True, "tools": False})
    warnings = sm.validate()
    assert any("tools" in w.lower() for w in warnings)


def test_validate_no_warnings_when_consistent():
    sm = ServiceManager({"agents": True, "tools": True})
    warnings = sm.validate()
    assert len(warnings) == 0


def test_to_dict():
    sm = ServiceManager({"inference": False})
    d = sm.to_dict()
    assert d["inference"] is False
    assert d["api"] is True
    assert isinstance(d, dict)
