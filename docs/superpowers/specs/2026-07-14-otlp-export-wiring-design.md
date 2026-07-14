# Astromesh Core — Wire Up OTLP Export — Design

**Date:** 2026-07-14
**Status:** Approved (design)
**Scope:** core `astromesh` package only
**Relationship:** Spec A of two. Spec B (Orbit Observability: Cloud Monitoring dashboard,
OTel Collector sidecar → Cloud Trace, `orbit logs`, `orbit upgrade`) depends on this and
follows separately.

---

## Summary

Astromesh ships a complete OpenTelemetry export path — `TelemetryManager` (OTLP spans),
`MetricsManager` (OTLP metrics), and `OTLPCollector` — but **none of it is ever wired up**.
Nothing is constructed, nothing is enabled, and nothing is exported. This spec connects the
existing pieces so that traces and metrics actually leave the process when OTLP export is
enabled, and makes that enablement possible from the environment (which containerized
deployments require).

This is the prerequisite for Orbit's Cloud Trace support: a collector sidecar is pointless
if the application never emits anything to it.

---

## Background: What Is Actually Broken

Verified against the code (not the docs):

| Component | Reality |
|---|---|
| `TelemetryManager` (`observability/telemetry.py`) | **Never instantiated.** `setup()` is never called. Referenced only as a `TYPE_CHECKING` hint in `collector.py`. |
| `MetricsManager` (`observability/metrics_export.py`) | **Never constructed.** `set_manager()` has **zero callers**, so `get_manager()` always returns `None` — the engine's metric recording (`engine.py:625`, `engine.py:774`) is a silent **no-op**. |
| `OTLPCollector` (`observability/collector.py`) | **Never instantiated.** Mentioned only in a comment in `engine.py:764`. |
| `TelemetryConfig.from_env_and_dict` / `MetricsConfig.from_env_and_dict` | **Zero callers.** |
| Active trace collector | `api/routes/traces.py:6` hardcodes `_collector: Collector = InternalCollector()` (in-memory). |
| `runtime.yaml` `spec.observability` | **Never loaded.** No code reads `runtime.yaml` into the runtime; `from_env_and_dict` expects a dict that never arrives. |

Net effect: agent traces go to an in-memory `InternalCollector` (served at `/v1/traces`), and
**nothing is ever exported over OTLP**. Metrics are not exported at all.

### The enablement gap

`from_env_and_dict` derives `enabled` **only** from the dict:

```python
enabled=bool(otlp.get("enabled", False))
```

`OTEL_EXPORTER_OTLP_ENDPOINT` sets the *endpoint* but cannot *enable* export. Since the dict
never arrives (no `runtime.yaml` loading), there is today **no way at all** to turn OTLP
export on — least of all in a container, where environment variables are the only lever.

---

## Design

### 1. New module: `astromesh/observability/setup.py`

A single, idempotent entry point that owns all the wiring. One responsibility: given an
optional observability dict, decide whether OTLP export is on and, if so, connect the three
dead components.

```python
def setup_observability(observability: dict | None = None) -> bool:
    """Wire OTLP export if enabled. Idempotent; safe to call more than once.

    Returns True if OTLP export was enabled and wired, False otherwise.

    When enabled:
      - TelemetryManager(cfg).setup()          → TracerProvider + OTLPSpanExporter
      - set_collector(OTLPCollector(manager))  → replaces the in-memory InternalCollector
      - set_manager(MetricsManager(...))       → engine's get_manager() stops returning None
    """
```

When OTLP is **not** enabled, the function does nothing: the `InternalCollector` stays in
place and `get_manager()` keeps returning `None`. **Default behavior is unchanged.**

### 2. Environment-driven enablement

Fix `from_env_and_dict` in **both** `TelemetryConfig` and `MetricsConfig` to honor an
environment variable, so containers can enable export:

- **`ASTROMESH_OTLP_ENABLED`** — new. Truthy (`1`, `true`, `yes`, case-insensitive) enables export.
- Precedence for `enabled`: explicit dict value (`observability.otlp.enabled`) > `ASTROMESH_OTLP_ENABLED` env > `False`.
- Precedence for `endpoint` (unchanged, already implemented): dict `endpoint` > `OTEL_EXPORTER_OTLP_ENDPOINT` env > `http://localhost:4317`.

The dict path is retained for programmatic/embedded use; the env path is what makes
containerized deployment (and Orbit's sidecar) possible.

### 3. Call site

`setup_observability()` is called as the **first statement** of `AgentRuntime.bootstrap()`
(`runtime/engine.py:179`) — **before** its early returns:

```python
async def bootstrap(self):
    setup_observability()                      # <-- new, before the early returns
    if self.service_manager and not self.service_manager.is_enabled("agents"):
        return
    agents_dir = self._config_dir / "agents"
    if not agents_dir.exists():
        return
    ...
```

This matters: `bootstrap()` returns early when the `agents` service is disabled or the agents
directory is absent. Wiring observability after those returns would leave such deployments
silently untraced. `bootstrap()` is the common path for both the API lifespan and
`astromeshd`, so one call site covers every entrypoint.

### 4. Why `OTLPCollector` and not a replacement

`OTLPCollector` **subclasses** `InternalCollector`: its `emit_trace` calls `super().emit_trace(ctx)`
(keeping the in-memory ring buffer) and *then* forwards spans to OpenTelemetry. Swapping it in
via the existing `set_collector()` therefore preserves `/v1/traces` exactly as it behaves
today while adding export. No route changes, no API changes.

### 5. Graceful degradation

Both managers already guard their setup:
- `TelemetryManager.setup()` catches `ImportError` (e.g. the `observability` extra is not
  installed, or grpcio's C extension can't load) and logs a warning; `get_tracer()` returns
  `None` and `OTLPCollector` skips forwarding.
- `MetricsManager.setup()` catches broad `Exception` and logs a warning, leaving its
  instruments `None` (its `record*` methods already null-check).

`setup_observability()` adds no new failure mode: with OTLP enabled but the OTel packages
missing, the runtime keeps working and logs warnings. Nothing raises into `bootstrap()`.

---

## Data Flow (after this change, with OTLP enabled)

```
Agent run → TracingContext (in-process spans)
  → engine finally-block → get_collector().emit_trace(ctx)
      → OTLPCollector.emit_trace
          → InternalCollector ring buffer  (still serves GET /v1/traces)
          → TelemetryManager tracer → BatchSpanProcessor → OTLPSpanExporter → endpoint
  → engine finally-block → get_manager().record_run(ctx) + .flush()
      → MetricsManager → PeriodicExportingMetricReader → OTLPMetricExporter → endpoint
```

With OTLP disabled (the default), the first branch stops at the ring buffer and
`get_manager()` returns `None` — identical to today.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| OTLP disabled (default) | No managers constructed; `InternalCollector` retained; zero behavior change. |
| OTLP enabled, `observability` extra not installed | `TelemetryManager.setup()` / `MetricsManager.setup()` catch the ImportError/Exception, log a warning; runtime keeps serving. |
| OTLP enabled, endpoint unreachable | `BatchSpanProcessor` / `PeriodicExportingMetricReader` are lazy — they do not connect at setup. Export failures are swallowed by the OTel SDK at export time; the run is unaffected. |
| `setup_observability()` called twice | Idempotent: guarded by a module-level flag; the second call is a no-op. |

---

## Testing

All tests are offline — no network, no live OTLP endpoint. `BatchSpanProcessor` and
`PeriodicExportingMetricReader` do not connect at construction, so wiring against a bogus
endpoint is safe.

**`TelemetryConfig` / `MetricsConfig` enablement (`from_env_and_dict`):**
- dict `otlp.enabled: true` → `enabled is True`.
- no dict, `ASTROMESH_OTLP_ENABLED=1` (monkeypatched env) → `enabled is True`.
- no dict, no env → `enabled is False` (regression guard for the default).
- dict `otlp.enabled: false` + `ASTROMESH_OTLP_ENABLED=1` → `enabled is False` (dict wins).
- endpoint precedence: dict > `OTEL_EXPORTER_OTLP_ENDPOINT` > default.

**`setup_observability()`:**
- disabled → `get_collector()` is an `InternalCollector` (and NOT an `OTLPCollector`);
  `get_manager()` is `None`.
- enabled → `get_collector()` is an `OTLPCollector`; `get_manager()` is not `None`.
- idempotent → calling twice leaves a single wired collector/manager and does not raise.
- Tests restore the module globals (`set_collector(InternalCollector())`, `set_manager(None)`)
  in teardown so they cannot leak into other tests.

**Integration:**
- `AgentRuntime.bootstrap()` calls `setup_observability()` even when the agents directory is
  absent (assert the wiring happened despite the early return).

---

## Out of Scope (explicit)

- GCP specifics — the OTel Collector sidecar, Cloud Monitoring dashboard, IAM, `orbit logs`,
  `orbit upgrade`. That is **Spec B (Orbit Observability)**, which depends on this one.
- Loading `runtime.yaml` into the runtime (a real gap, but a separate concern: the env path
  is what deployments need, and the dict path already exists for programmatic callers).
- Replacing the in-memory `/v1/traces` collector or changing its API.
- Prometheus-format `/v1/metrics` (the route's in-memory counters stay as they are).

---

## Component Boundaries

- **`observability/setup.py`** — decides enablement and performs the wiring. Interface:
  `setup_observability(observability: dict | None) -> bool`. Depends on telemetry,
  metrics_export, collector, and the traces route's `set_collector`. The only module that
  knows how the pieces fit together.
- **`observability/telemetry.py` / `metrics_export.py`** — unchanged except that
  `from_env_and_dict` gains the `ASTROMESH_OTLP_ENABLED` env fallback. Still pure config +
  manager, no knowledge of the runtime.
- **`runtime/engine.py`** — gains exactly one line (the call). It does not know how
  observability is wired, only that it must be wired before bootstrap proceeds.
