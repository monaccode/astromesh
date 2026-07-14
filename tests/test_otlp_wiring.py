"""setup_observability(): connects TelemetryManager / MetricsManager / OTLPCollector.

Without it these three exist but are never constructed, so nothing is ever exported.
"""

import pytest

from astromesh.api.routes.traces import get_collector
from astromesh.observability.collector import InternalCollector, OTLPCollector
from astromesh.observability.metrics_export import get_manager
from astromesh.observability.setup import reset_observability, setup_observability


@pytest.fixture(autouse=True)
def _clean_observability():
    """Wiring is process-global — restore the default state around every test."""
    reset_observability()
    yield
    reset_observability()


def test_disabled_leaves_defaults(monkeypatch):
    monkeypatch.delenv("ASTROMESH_OTLP_ENABLED", raising=False)
    assert setup_observability({}) is False
    collector = get_collector()
    assert isinstance(collector, InternalCollector)
    assert not isinstance(collector, OTLPCollector)
    assert get_manager() is None


def test_enabled_via_env_wires_otlp(monkeypatch):
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert setup_observability({}) is True
    assert isinstance(get_collector(), OTLPCollector)
    assert get_manager() is not None


def test_enabled_via_dict_wires_otlp(monkeypatch):
    monkeypatch.delenv("ASTROMESH_OTLP_ENABLED", raising=False)
    assert setup_observability({"otlp": {"enabled": True}}) is True
    assert isinstance(get_collector(), OTLPCollector)
    assert get_manager() is not None


def test_idempotent(monkeypatch):
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert setup_observability({}) is True
    first_collector = get_collector()
    first_manager = get_manager()
    assert setup_observability({}) is True
    assert get_collector() is first_collector
    assert get_manager() is first_manager


def test_reset_restores_defaults(monkeypatch):
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    setup_observability({})
    reset_observability()
    assert isinstance(get_collector(), InternalCollector)
    assert not isinstance(get_collector(), OTLPCollector)
    assert get_manager() is None
