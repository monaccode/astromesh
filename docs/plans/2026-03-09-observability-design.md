# Astromesh Helm Chart Phase 3: Observability Subcharts Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/helm-chart

---

## Overview

Add kube-prometheus-stack and OpenTelemetry Collector as optional subchart dependencies. Disabled by default, enabled in dev for plug-and-play observability in dedicated clusters.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Prometheus + Grafana | kube-prometheus-stack (single subchart) | Industry standard, bundles everything |
| OTel Collector | opentelemetry-collector subchart | Astromesh-specific config, pre-wired |
| Grafana dashboards | Deferred to future phase | Metrics need to stabilize first |
| Auto-wiring | OTel endpoint resolves to collector subchart | Zero-config for deployer |

## New Dependencies (Chart.yaml)

| Subchart | Repository | Condition |
|----------|-----------|-----------|
| `kube-prometheus-stack` | prometheus-community | `kube-prometheus-stack.enabled` |
| `opentelemetry-collector` | open-telemetry | `opentelemetry-collector.enabled` |

## Auto-Wiring

New helper `astromesh.otel.endpoint` in `_helpers.tpl`:
- If `opentelemetry-collector.enabled`: resolves to `{{ .Release.Name }}-opentelemetry-collector:4317`
- Otherwise: uses `observability.otel.endpoint` from values

Deployment template uses this helper instead of raw value.

## Environment Values

- `values-dev.yaml`: Enable both subcharts + OTel auto-wiring
- `values-prod.yaml`: No changes (external stack assumed)
