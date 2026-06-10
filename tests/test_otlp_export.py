"""Fase 4.3: OTLP export activation — config precedence + engine emits traces to the active collector."""

import pytest

from astromesh.observability.telemetry import TelemetryConfig


def test_endpoint_from_env(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example:4317")
    cfg = TelemetryConfig.from_env_and_dict({})
    assert cfg.otlp_endpoint == "http://collector.example:4317"
    # env alone does not enable export — only observability.otlp.enabled does.
    assert cfg.enabled is False


def test_endpoint_dict_overrides_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    cfg = TelemetryConfig.from_env_and_dict({"otlp": {"endpoint": "http://x:4317", "enabled": True}})
    assert cfg.otlp_endpoint == "http://x:4317"
    assert cfg.enabled is True


def test_endpoint_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    cfg = TelemetryConfig.from_env_and_dict({})
    assert cfg.otlp_endpoint == "http://localhost:4317"
    assert cfg.enabled is False
