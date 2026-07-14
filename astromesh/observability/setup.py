"""Wires OTLP export.

The only module that knows how TelemetryManager, MetricsManager and the trace collector fit
together. Without it, all three exist but are never constructed and nothing is exported.

Imports are done lazily inside the functions: `astromesh.api.routes.traces` pulls in FastAPI,
and the runtime must not take that at import time (the engine already imports it lazily).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_wired = False


def setup_observability(observability: dict | None = None) -> bool:
    """Wire OTLP export when enabled. Idempotent; safe to call more than once.

    Returns True when export is wired, False when OTLP is disabled — in which case nothing is
    touched: the in-memory InternalCollector and a None metrics manager remain in place.
    """
    global _wired
    if _wired:
        return True

    from astromesh.observability.telemetry import TelemetryConfig, TelemetryManager

    tcfg = TelemetryConfig.from_env_and_dict(observability or {})
    if not tcfg.enabled:
        return False

    from astromesh.api.routes.traces import set_collector
    from astromesh.observability.collector import OTLPCollector
    from astromesh.observability.metrics_export import (
        MetricsConfig,
        MetricsManager,
        set_manager,
    )

    telemetry = TelemetryManager(tcfg)
    telemetry.setup()
    # OTLPCollector subclasses InternalCollector: GET /v1/traces keeps working, and spans are
    # additionally forwarded to OpenTelemetry.
    set_collector(OTLPCollector(telemetry_manager=telemetry))

    mcfg = MetricsConfig.from_env_and_dict(observability or {})
    metrics = MetricsManager(endpoint=mcfg.endpoint, enabled=mcfg.enabled)
    metrics.setup()
    set_manager(metrics)

    _wired = True
    logger.info("OTLP export enabled — endpoint=%s", tcfg.otlp_endpoint)
    return True


def reset_observability() -> None:
    """Restore the default, unwired state (in-memory collector, no metrics manager).

    Wiring is process-global; tests use this to keep it from leaking between them.
    """
    global _wired

    from astromesh.api.routes.traces import set_collector
    from astromesh.observability.collector import InternalCollector
    from astromesh.observability.metrics_export import set_manager

    set_collector(InternalCollector())
    set_manager(None)
    _wired = False
