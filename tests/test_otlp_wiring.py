"""setup_observability(): connects TelemetryManager / MetricsManager / OTLPCollector.

Without it these three exist but are never constructed, so nothing is ever exported.
"""

import pytest

from astromesh.api.routes.traces import get_collector, set_collector
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


def test_wiring_failure_falls_back_to_defaults(monkeypatch):
    """A failure while wiring must not raise into bootstrap, and must leave clean defaults."""
    from astromesh.observability import telemetry as telemetry_mod

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")

    def boom(self):
        raise RuntimeError("exporter exploded")

    monkeypatch.setattr(telemetry_mod.TelemetryManager, "setup", boom)

    assert setup_observability({}) is False  # does not raise
    collector = get_collector()
    assert isinstance(collector, InternalCollector)
    assert not isinstance(collector, OTLPCollector)
    assert get_manager() is None


def test_malformed_observability_config_does_not_raise(monkeypatch):
    """A malformed spec.observability must not kill bootstrap, and must not touch the collector."""
    monkeypatch.delenv("ASTROMESH_OTLP_ENABLED", raising=False)
    sentinel = InternalCollector()
    set_collector(sentinel)

    # "otlp" is a scalar where a mapping is expected -> .get() would raise AttributeError
    assert setup_observability({"otlp": "yes"}) is False

    assert get_collector() is sentinel  # zero-touch invariant preserved
    assert get_manager() is None


async def test_bootstrap_wires_observability_before_early_return(tmp_path, monkeypatch):
    """bootstrap() early-returns when there is no agents/ dir — observability must be wired anyway."""
    from astromesh.runtime.engine import AgentRuntime

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert not (tmp_path / "agents").exists()  # forces the early return

    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert isinstance(get_collector(), OTLPCollector)
    assert get_manager() is not None


async def test_bootstrap_leaves_defaults_when_disabled(tmp_path, monkeypatch):
    from astromesh.runtime.engine import AgentRuntime

    monkeypatch.delenv("ASTROMESH_OTLP_ENABLED", raising=False)
    runtime = AgentRuntime(config_dir=str(tmp_path))
    await runtime.bootstrap()

    assert isinstance(get_collector(), InternalCollector)
    assert not isinstance(get_collector(), OTLPCollector)
    assert get_manager() is None


async def test_bootstrap_wires_from_observability_dict(tmp_path, monkeypatch):
    """runtime.yaml's spec.observability now reaches setup_observability via AgentRuntime."""
    from astromesh.runtime.engine import AgentRuntime

    monkeypatch.delenv("ASTROMESH_OTLP_ENABLED", raising=False)
    runtime = AgentRuntime(
        config_dir=str(tmp_path),
        observability={"otlp": {"enabled": True, "endpoint": "http://collector:4317"}},
    )
    await runtime.bootstrap()

    assert isinstance(get_collector(), OTLPCollector)
    assert get_manager() is not None


async def test_bootstrap_dict_disabled_beats_env(tmp_path, monkeypatch):
    """An explicit observability dict that disables OTLP wins over the env var."""
    from astromesh.runtime.engine import AgentRuntime

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    runtime = AgentRuntime(config_dir=str(tmp_path), observability={"otlp": {"enabled": False}})
    await runtime.bootstrap()

    assert isinstance(get_collector(), InternalCollector)
    assert not isinstance(get_collector(), OTLPCollector)
    assert get_manager() is None
