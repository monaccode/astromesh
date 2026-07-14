# OTLP Export Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make astromesh actually export traces and metrics over OTLP by connecting the three components that exist but are never constructed (`TelemetryManager`, `MetricsManager`, `OTLPCollector`), and make that enablement possible from the environment.

**Architecture:** A new `astromesh/observability/setup.py` owns all the wiring behind one idempotent entry point, `setup_observability()`. It is called as the first statement of `AgentRuntime.bootstrap()` — before that method's early returns — so every entrypoint (API lifespan, `astromeshd`) gets it. A new `ASTROMESH_OTLP_ENABLED` env var provides the enable switch that containers need; today `enabled` can only come from a dict that nothing ever supplies.

**Tech Stack:** Python 3.12+, OpenTelemetry SDK + OTLP gRPC exporter (the `observability` extra), pytest (`asyncio_mode = "auto"`), uv, ruff.

## Global Constraints

- Run tests from the repo root with: `uv run pytest -q`. Lint: `uv run ruff check astromesh/ tests/`; format: `uv run ruff format --check astromesh/ tests/`. Ruff line-length 100, target py312.
- **There are TWO different `MetricsConfig` classes.** The one this plan changes lives in `astromesh/observability/metrics_export.py` (paired with `MetricsManager`). Do **not** touch the unrelated `MetricsConfig` in `astromesh/observability/metrics.py` (paired with `MetricsCollector`).
- **Default behavior must not change.** With OTLP disabled (the default), `get_collector()` must remain an `InternalCollector` and `get_manager()` must remain `None`.
- **An existing test must keep passing:** `tests/test_otlp_export.py::test_endpoint_from_env` asserts that setting `OTEL_EXPORTER_OTLP_ENDPOINT` alone does **not** enable export. The new enable switch is a **separate** variable, `ASTROMESH_OTLP_ENABLED` — the endpoint variable must never imply "enabled".
- Enable precedence: explicit dict `observability.otlp.enabled` (even when `false`) > `ASTROMESH_OTLP_ENABLED` env > `False`.
- Endpoint precedence (already implemented, do not change): dict `endpoint` > `OTEL_EXPORTER_OTLP_ENDPOINT` env > `http://localhost:4317` (telemetry) / `http://127.0.0.1:4317` (metrics).
- Truthy env values for `ASTROMESH_OTLP_ENABLED`: `1`, `true`, `yes` — case-insensitive, whitespace-stripped.
- Per CLAUDE.md, a `feat:` commit requires a `CHANGELOG.md` entry in the same or an immediately preceding commit. Task 1 carries the entry for this whole feature.

---

## File Structure

**Create:**
- `astromesh/observability/env.py` — parses `ASTROMESH_OTLP_ENABLED`. Shared by both config builders so the truthy logic is not duplicated.
- `astromesh/observability/setup.py` — the only module that knows how telemetry, metrics and the trace collector fit together. Exposes `setup_observability()` and `reset_observability()`.
- `tests/test_otlp_wiring.py` — tests for `setup_observability()`.

**Modify:**
- `astromesh/observability/telemetry.py` — `TelemetryConfig.from_env_and_dict` honors the env enable var.
- `astromesh/observability/metrics_export.py` — `MetricsConfig.from_env_and_dict` honors the env enable var.
- `astromesh/runtime/engine.py` — `AgentRuntime.bootstrap()` calls `setup_observability()` first.
- `tests/test_otlp_export.py` — add env-enablement cases alongside the existing precedence tests.
- `docs-site/src/content/docs/advanced/observability.md` — document the env switch.
- `CHANGELOG.md` — feature entry (Task 1).

---

### Task 1: Env-driven enablement (`ASTROMESH_OTLP_ENABLED`)

Today `enabled` is derived **only** from the dict (`enabled=bool(otlp.get("enabled", False))`), and nothing ever supplies that dict — so OTLP export cannot be turned on at all, least of all in a container. This task adds the env switch to both config builders.

**Files:**
- Create: `astromesh/observability/env.py`
- Modify: `astromesh/observability/telemetry.py` (the `from_env_and_dict` classmethod)
- Modify: `astromesh/observability/metrics_export.py` (the `from_env_and_dict` classmethod)
- Modify: `tests/test_otlp_export.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `astromesh.observability.env.OTLP_ENABLED_ENV: str` (the literal `"ASTROMESH_OTLP_ENABLED"`)
  - `astromesh.observability.env.otlp_enabled_from_env() -> bool`
  - `TelemetryConfig.from_env_and_dict(observability: dict) -> TelemetryConfig` — unchanged signature; `enabled` now also honors the env var.
  - `MetricsConfig.from_env_and_dict(observability: dict) -> MetricsConfig` (the one in `metrics_export.py`) — same.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_otlp_export.py`:

```python
def test_enabled_from_astromesh_env(monkeypatch):
    """ASTROMESH_OTLP_ENABLED turns export on when the dict says nothing."""
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert TelemetryConfig.from_env_and_dict({}).enabled is True


def test_enabled_env_truthy_variants(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", " Yes "):
        monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", value)
        assert TelemetryConfig.from_env_and_dict({}).enabled is True, value


def test_enabled_env_falsy_variants(monkeypatch):
    for value in ("0", "false", "no", ""):
        monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", value)
        assert TelemetryConfig.from_env_and_dict({}).enabled is False, value


def test_dict_enabled_false_beats_env(monkeypatch):
    """An explicit dict value wins over the env var, even when it disables export."""
    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert TelemetryConfig.from_env_and_dict({"otlp": {"enabled": False}}).enabled is False


def test_metrics_config_enabled_from_astromesh_env(monkeypatch):
    from astromesh.observability.metrics_export import MetricsConfig

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert MetricsConfig.from_env_and_dict({}).enabled is True


def test_metrics_config_dict_enabled_false_beats_env(monkeypatch):
    from astromesh.observability.metrics_export import MetricsConfig

    monkeypatch.setenv("ASTROMESH_OTLP_ENABLED", "1")
    assert MetricsConfig.from_env_and_dict({"otlp": {"enabled": False}}).enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_otlp_export.py -q`
Expected: FAIL — the new tests assert `enabled is True` but get `False` (the env var is ignored today).

- [ ] **Step 3: Create the shared env helper**

Create `astromesh/observability/env.py`:

```python
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
```

- [ ] **Step 4: Honor the env var in `TelemetryConfig`**

In `astromesh/observability/telemetry.py`, add this import at the top of the file (after `import os`):

```python
from astromesh.observability.env import otlp_enabled_from_env
```

Then replace the body of `TelemetryConfig.from_env_and_dict` so the `return` reads:

```python
    @classmethod
    def from_env_and_dict(cls, observability: dict) -> "TelemetryConfig":
        """Build from a runtime.yaml spec.observability dict + env. Export is OFF by default.
        Enable precedence: explicit observability.otlp.enabled > ASTROMESH_OTLP_ENABLED env >
        off. Endpoint precedence: explicit dict endpoint > OTEL_EXPORTER_OTLP_ENDPOINT env >
        localhost:4317 (the node-local collector default). Note OTEL_EXPORTER_OTLP_ENDPOINT sets
        only the endpoint — it never enables export.
        """
        otlp = (observability or {}).get("otlp", {}) or {}
        endpoint = (
            otlp.get("endpoint")
            or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
            or "http://localhost:4317"
        )
        enabled = otlp.get("enabled")
        if enabled is None:
            enabled = otlp_enabled_from_env()
        return cls(
            otlp_endpoint=endpoint,
            enabled=bool(enabled),
        )
```

(`otlp.get("enabled")` returns `None` only when the key is absent, so an explicit `false` in the dict still wins over the env var.)

- [ ] **Step 5: Honor the env var in `MetricsConfig` (metrics_export.py)**

In `astromesh/observability/metrics_export.py`, add this import at the top (after `import os`):

```python
from astromesh.observability.env import otlp_enabled_from_env
```

Then replace `MetricsConfig.from_env_and_dict` with:

```python
    @classmethod
    def from_env_and_dict(cls, observability: dict) -> "MetricsConfig":
        otlp = (observability or {}).get("otlp", {}) or {}
        endpoint = (
            otlp.get("endpoint")
            or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
            or "http://127.0.0.1:4317"
        )
        enabled = otlp.get("enabled")
        if enabled is None:
            enabled = otlp_enabled_from_env()
        return cls(endpoint=endpoint, enabled=bool(enabled))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_otlp_export.py -q`
Expected: PASS — including the pre-existing `test_endpoint_from_env`, which must still assert that `OTEL_EXPORTER_OTLP_ENDPOINT` alone leaves `enabled is False`.

- [ ] **Step 7: Add the CHANGELOG entry**

In `CHANGELOG.md`, under `## [Unreleased]`, add this subsection immediately below the `## [Unreleased]` line:

```markdown
### Fixed (Observability)
- **OTLP export was never wired up.** `TelemetryManager`, `MetricsManager` and `OTLPCollector`
  all existed but were never constructed: `set_manager()` had zero callers (so the engine's
  metric recording was a silent no-op), the trace collector was hardcoded to the in-memory
  `InternalCollector`, and `enabled` could only come from a `runtime.yaml` dict that nothing
  ever loaded — so there was no way to turn export on at all. Added
  `astromesh/observability/setup.py` (`setup_observability()`), called from
  `AgentRuntime.bootstrap()` before its early returns, which starts the `TelemetryManager`,
  installs an `OTLPCollector` (still backing `GET /v1/traces`) and registers the
  `MetricsManager`. Added the `ASTROMESH_OTLP_ENABLED` env var so containerized deployments can
  enable export. Default behavior is unchanged: with OTLP off, traces stay in the in-memory
  collector and nothing is exported.
```

- [ ] **Step 8: Commit**

```bash
git add astromesh/observability/env.py astromesh/observability/telemetry.py astromesh/observability/metrics_export.py tests/test_otlp_export.py CHANGELOG.md
git commit -m "feat(observability): enable OTLP export from the environment"
```

---

### Task 2: `setup_observability()` — the wiring module

**Files:**
- Create: `astromesh/observability/setup.py`
- Create: `tests/test_otlp_wiring.py`

**Interfaces:**
- Consumes (all already exist):
  - `TelemetryConfig.from_env_and_dict(dict) -> TelemetryConfig` with fields `.enabled: bool`, `.otlp_endpoint: str`; `TelemetryManager(config)` with `.setup()`.
  - `MetricsConfig.from_env_and_dict(dict) -> MetricsConfig` with fields `.enabled: bool`, `.endpoint: str` (from `metrics_export.py`); `MetricsManager(endpoint: str, enabled: bool)` with `.setup()`; `set_manager(m) -> None`; `get_manager() -> MetricsManager | None`.
  - `astromesh.api.routes.traces.set_collector(collector) -> None` and `get_collector() -> Collector`.
  - `astromesh.observability.collector.InternalCollector`, `OTLPCollector(telemetry_manager=...)` — `OTLPCollector` subclasses `InternalCollector`, so swapping it in keeps `GET /v1/traces` working.
- Produces:
  - `astromesh.observability.setup.setup_observability(observability: dict | None = None) -> bool`
  - `astromesh.observability.setup.reset_observability() -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_otlp_wiring.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_otlp_wiring.py -q`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'astromesh.observability.setup'`.

- [ ] **Step 3: Write the wiring module**

Create `astromesh/observability/setup.py`:

```python
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
```

Note: `TelemetryManager.setup()` already catches `ImportError` and `MetricsManager.setup()` catches broad `Exception` — if the `observability` extra is not installed, both log a warning and leave their exporters unset. The collector and manager are still installed, so nothing raises into the caller.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_otlp_wiring.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite to check for cross-test leakage**

Run: `uv run pytest -q`
Expected: PASS — in particular `tests/test_otlp_export.py::test_engine_emits_trace_to_collector` and `tests/test_traces_api.py` must still pass (they set their own collector; with OTLP disabled `setup_observability()` does not touch it).

- [ ] **Step 6: Commit**

```bash
git add astromesh/observability/setup.py tests/test_otlp_wiring.py
git commit -m "feat(observability): add setup_observability() to wire OTLP export"
```

---

### Task 3: Call it from `AgentRuntime.bootstrap()`

`bootstrap()` returns early when the `agents` service is disabled or the agents directory is missing. The wiring call must therefore be the **first statement**, or such deployments would silently run untraced.

**Files:**
- Modify: `astromesh/runtime/engine.py` (`AgentRuntime.bootstrap`, at line 179)
- Modify: `tests/test_otlp_wiring.py`

**Interfaces:**
- Consumes: `setup_observability()` and `reset_observability()` from Task 2.
- Produces: every entrypoint that bootstraps the runtime (API lifespan, `astromeshd`) wires observability.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_otlp_wiring.py`:

```python
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
```

(The `_clean_observability` autouse fixture already in this file resets the global state around each test.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_otlp_wiring.py::test_bootstrap_wires_observability_before_early_return -q`
Expected: FAIL — `assert isinstance(get_collector(), OTLPCollector)` fails; the collector is still an `InternalCollector` because `bootstrap()` never wires anything.

- [ ] **Step 3: Call `setup_observability()` first in `bootstrap()`**

In `astromesh/runtime/engine.py`, change `AgentRuntime.bootstrap` from:

```python
    async def bootstrap(self):
        # Skip agent loading if agents service is disabled
        if self.service_manager and not self.service_manager.is_enabled("agents"):
            return
```

to:

```python
    async def bootstrap(self):
        # Wire OTLP export FIRST: the early returns below must not leave a deployment untraced.
        # Imported lazily — the module pulls in the traces route (FastAPI) on the enabled path.
        from astromesh.observability.setup import setup_observability

        setup_observability()

        # Skip agent loading if agents service is disabled
        if self.service_manager and not self.service_manager.is_enabled("agents"):
            return
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_otlp_wiring.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS. `bootstrap()` is called by many tests; with OTLP disabled (no `ASTROMESH_OTLP_ENABLED` in the environment) `setup_observability()` is a no-op, so none of them change behavior.

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/`
Expected: `All checks passed!` and `N files already formatted`.

- [ ] **Step 7: Commit**

```bash
git add astromesh/runtime/engine.py tests/test_otlp_wiring.py
git commit -m "feat(observability): wire OTLP export at runtime bootstrap"
```

---

### Task 4: Document the env switch

**Files:**
- Modify: `docs-site/src/content/docs/advanced/observability.md`

**Interfaces:**
- Consumes: `ASTROMESH_OTLP_ENABLED` (Task 1), automatic wiring at bootstrap (Task 3).

- [ ] **Step 1: Document enabling export**

The page's `## Tracing (OpenTelemetry)` → `### Configuration` section (around line 39-55) currently shows only `OTEL_EXPORTER_OTLP_ENDPOINT` and a hand-constructed `TelemetryConfig`. Add, in that section, the supported deployment path — matching the page's existing heading levels and code-fence style:

````markdown
Export is **off by default**. Turn it on with `ASTROMESH_OTLP_ENABLED`; the runtime wires it
automatically at bootstrap (starting the `TelemetryManager`, installing an `OTLPCollector`, and
registering the `MetricsManager`):

```bash
export ASTROMESH_OTLP_ENABLED=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # optional; this is the default
```

`OTEL_EXPORTER_OTLP_ENDPOINT` sets only the endpoint — it never enables export on its own.
An explicit `observability.otlp.enabled` value takes precedence over the env var.
````

Then, in the `### Collectors` area (around lines 141-153, where `OTLPCollector` is shown being constructed by hand), add this note immediately after that code block:

```markdown
> The runtime installs `OTLPCollector` for you when OTLP export is enabled — see
> `ASTROMESH_OTLP_ENABLED` above. Constructing it by hand, as shown, is only needed when
> embedding Astromesh programmatically.
```

- [ ] **Step 2: Verify the docs site builds**

Run: `cd docs-site && npm run build 2>&1 | tail -3`
Expected: build completes ("Complete!"), no MDX/markdown errors.

- [ ] **Step 3: Commit**

```bash
git add docs-site/src/content/docs/advanced/observability.md
git commit -m "docs(observability): document ASTROMESH_OTLP_ENABLED and automatic wiring"
```

---

## Final Verification

- [ ] `uv run pytest -q` → all green (the suite was green before this work; no test may regress).
- [ ] `uv run ruff check astromesh/ tests/` → `All checks passed!`
- [ ] `uv run ruff format --check astromesh/ tests/` → all formatted.
- [ ] `grep -rn "set_manager\|OTLPCollector(" astromesh/observability/setup.py` → both are now actually called (they had zero callers before).
- [ ] Default-off proof: with no `ASTROMESH_OTLP_ENABLED` set, `tests/test_traces_api.py` and `tests/test_otlp_export.py::test_engine_emits_trace_to_collector` still pass unchanged.
- [ ] `cd docs-site && npm run build` → Complete!
