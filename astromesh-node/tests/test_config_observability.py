"""Fase 4.3: DaemonConfig parses spec.observability (OTLP export config)."""

from astromesh_node.daemon.config import DaemonConfig


def test_observability_defaults_empty():
    cfg = DaemonConfig.from_dict({"spec": {}})
    assert cfg.observability == {}


def test_observability_otlp_parsed():
    cfg = DaemonConfig.from_dict(
        {"spec": {"observability": {"otlp": {"enabled": True, "endpoint": "http://localhost:4317"}}}}
    )
    assert cfg.observability["otlp"]["enabled"] is True
    assert cfg.observability["otlp"]["endpoint"] == "http://localhost:4317"
