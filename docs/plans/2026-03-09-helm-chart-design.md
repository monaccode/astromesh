# Astromesh Helm Chart Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/helm-chart

---

## Overview

Production-grade Helm chart for deploying Astromesh on Kubernetes. The approach is incremental: MVP chart with core functionality first, advanced features documented for future phases.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | MVP + full plan documented | Functional chart fast, vision for future |
| Infrastructure deps | Hybrid (Bitnami subcharts + external option) | Covers dev and production scenarios |
| Chart location | `deploy/helm/astromesh/` | Room for future kustomize/terraform in `deploy/` |
| Model serving | Ollama only (optional subchart) | Simplest for MVP, document others as external |
| Ingress | Standard K8s Ingress | Covers 90% of cases, controller-agnostic |
| Observability | Instrumentation only (no subcharts) | Clusters usually have existing monitoring stack |

## Chart Structure

```
deploy/
└── helm/
    └── astromesh/
        ├── Chart.yaml
        ├── values.yaml
        ├── values-dev.yaml
        ├── values-staging.yaml
        ├── values-prod.yaml
        ├── templates/
        │   ├── _helpers.tpl
        │   ├── deployment.yaml
        │   ├── service.yaml
        │   ├── ingress.yaml
        │   ├── hpa.yaml
        │   ├── configmap-runtime.yaml
        │   ├── configmap-providers.yaml
        │   ├── configmap-channels.yaml
        │   ├── configmap-agents.yaml
        │   ├── secret.yaml
        │   ├── serviceaccount.yaml
        │   └── NOTES.txt
        └── charts/
```

## Dependencies

| Subchart | Source | Default | Purpose |
|----------|--------|---------|---------|
| `postgresql` | bitnami | enabled | Postgres + pgvector |
| `redis` | bitnami | enabled | Cache/memory backend |
| `ollama` | ollama-helm | disabled | Optional model serving |

Each can be disabled and replaced with external connection strings.

## ConfigMaps

Astromesh YAML configuration files from `config/` are mounted as ConfigMaps:

- **configmap-runtime** — `runtime.yaml` → `/app/config/runtime.yaml`
- **configmap-providers** — `providers.yaml` → `/app/config/providers.yaml`
- **configmap-channels** — `channels.yaml` → `/app/config/channels.yaml`
- **configmap-agents** — `*.agent.yaml` files → `/app/config/agents/`

Content is defined inline in `values.yaml`, allowing per-environment overrides.

## Secrets

Single Secret resource with:

- `OPENAI_API_KEY`
- `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN`
- `DATABASE_URL` (when using external Postgres)
- `REDIS_URL` (when using external Redis)

Supports both inline values and `existingSecret` reference.

## Deployment

- **Image:** From existing `Dockerfile` (`astromesh:0.4.0`)
- **Port:** 8000
- **Probes:** liveness/readiness on `/health`
- **Volumes:** ConfigMaps mounted at `/app/config/`
- **Env vars:** From Secret + OTel configuration
- **Resources:** Configurable requests/limits

## Ingress

- Disabled by default
- Configurable annotations (nginx, traefik, ALB, etc.)
- Optional TLS
- Configurable host

## HPA

- Disabled by default
- Min/max replicas configurable
- Target: CPU utilization 80%

## Observability (Instrumentation Only)

- Prometheus annotations on Service (`prometheus.io/scrape: "true"`)
- OTel collector endpoint via env vars
- No monitoring subcharts deployed

## Example values.yaml

```yaml
replicaCount: 1
image:
  repository: astromesh
  tag: "0.4.0"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: false
  className: ""
  annotations: {}
  hosts:
    - host: astromesh.local
      paths:
        - path: /
          pathType: Prefix
  tls: []

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 5
  targetCPUUtilizationPercentage: 80

config:
  runtime:
    api:
      host: "0.0.0.0"
      port: 8000
    defaults:
      orchestration_pattern: "react"
      max_iterations: 10
  providers: {}
  channels: {}
  agents: {}

secrets:
  create: true
  existingSecret: ""
  values:
    OPENAI_API_KEY: ""
    WHATSAPP_TOKEN: ""

observability:
  prometheus:
    enabled: true
  otel:
    enabled: false
    endpoint: "http://otel-collector:4317"

postgresql:
  enabled: true
  auth:
    database: astromesh
    username: astromesh
    password: ""
  primary:
    persistence:
      size: 10Gi

redis:
  enabled: true
  architecture: standalone
  auth:
    enabled: false

ollama:
  enabled: false
  service:
    port: 11434
```

## Future Phases

### Phase 2 — Extended Model Serving
- vLLM + HF TEI as optional subcharts
- GPU scheduling with nodeSelector/tolerations
- Model persistence volumes

### Phase 3 — Observability Subcharts
- kube-prometheus-stack as optional dependency
- OTel collector subchart
- Grafana dashboards for Astromesh metrics

### Phase 4 — GitOps
- ArgoCD ApplicationSet templates
- Multi-environment deployment pipelines
- Sealed Secrets or External Secrets Operator

### Phase 5 — External Secrets
- External Secrets Operator integration
- AWS Secrets Manager / GCP Secret Manager / Vault support

### Phase 6 — Kubernetes Operator
- CRDs: `Agent`, `Provider`, `Channel`, `RAGPipeline`
- Reconciliation logic for agent lifecycle
- Auto-scaling based on agent workload metrics
