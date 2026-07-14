"""Environment parsing for observability config.

Kept separate so both config builders (TelemetryConfig, MetricsConfig) share one
definition of "is OTLP export enabled by the environment".
"""

import os

OTLP_ENABLED_ENV = "ASTROMESH_OTLP_ENABLED"
_TRUTHY = {"1", "true", "yes"}


def otlp_enabled_from_env() -> bool:
    """True when ASTROMESH_OTLP_ENABLED is set to a truthy value (1/true/yes)."""
    return os.environ.get(OTLP_ENABLED_ENV, "").strip().lower() in _TRUTHY
