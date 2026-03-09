# Kubernetes Deployment Guide

This guide covers deploying Astromesh on Kubernetes using the Helm chart and optional GitOps with ArgoCD.

---

## Prerequisites

- Kubernetes 1.26+
- Helm 3.x
- `kubectl` configured for your cluster
- Docker image of Astromesh built and pushed to a registry

### Build the Docker image

```bash
cd docker
docker build -t your-registry/astromesh:0.4.0 -f Dockerfile ..
docker push your-registry/astromesh:0.4.0
```

---

## Quick Start

```bash
# Add dependency chart repositories
cd deploy/helm/astromesh
helm dependency update

# Install with default values (dev-friendly)
helm install astromesh . -f values-dev.yaml --namespace astromesh-dev --create-namespace

# Verify
kubectl get pods -n astromesh-dev
```

---

## Chart Structure

```
deploy/
├── helm/
│   └── astromesh/
│       ├── Chart.yaml              # Chart metadata and dependencies
│       ├── values.yaml             # Default configuration
│       ├── values-dev.yaml         # Development overrides
│       ├── values-staging.yaml     # Staging overrides
│       ├── values-prod.yaml        # Production overrides
│       ├── .helmignore
│       ├── charts/                 # Downloaded subchart tarballs
│       └── templates/
│           ├── _helpers.tpl        # Template helpers
│           ├── deployment.yaml     # Astromesh API deployment
│           ├── service.yaml        # API service + Prometheus annotations
│           ├── ingress.yaml        # Optional Ingress
│           ├── hpa.yaml            # Optional HorizontalPodAutoscaler
│           ├── configmap-runtime.yaml
│           ├── configmap-providers.yaml
│           ├── configmap-channels.yaml
│           ├── configmap-agents.yaml
│           ├── secret.yaml         # API keys and tokens
│           ├── secret-hf-token.yaml # HuggingFace token
│           ├── serviceaccount.yaml
│           ├── deployment-vllm.yaml  # Optional vLLM
│           ├── service-vllm.yaml
│           ├── deployment-tei.yaml   # Optional TEI instances
│           ├── service-tei.yaml
│           └── NOTES.txt
└── gitops/
    └── argocd/
        └── applicationset.yaml     # ArgoCD multi-environment deployment
```

---

## Dependencies

The chart includes these optional subchart dependencies:

| Subchart | Version | Default | Purpose |
|----------|---------|---------|---------|
| PostgreSQL (Bitnami) | ~16.0 | Enabled | Database + pgvector |
| Redis (Bitnami) | ~20.0 | Enabled | Cache and memory backend |
| Ollama | ~1.0 | Disabled | Local LLM inference |
| kube-prometheus-stack | ~67.0 | Disabled | Prometheus + Grafana + AlertManager |
| OpenTelemetry Collector | ~0.108 | Disabled | Trace and metrics collection |

Each dependency can be disabled and replaced with external services.

---

## Configuration

### Astromesh Config Files

The YAML configuration files from `config/` are mounted into the pod via ConfigMaps. Define their content inline in `values.yaml`:

```yaml
config:
  runtime: |
    apiVersion: astromesh/v1
    kind: RuntimeConfig
    ...

  providers: |
    apiVersion: astromesh/v1
    kind: ProviderConfig
    ...

  channels: |
    channels:
      whatsapp:
        ...

  agents:
    my-agent.agent.yaml: |
      apiVersion: astromesh/v1
      kind: Agent
      ...
```

These are mounted at `/app/config/` inside the container.

### Secrets

Two modes for managing secrets:

**Inline (development):**
```yaml
secrets:
  create: true
  values:
    OPENAI_API_KEY: "sk-..."
    WHATSAPP_ACCESS_TOKEN: "..."
```

**Existing Secret (production):**
```yaml
secrets:
  create: false
  existingSecret: my-existing-secret
```

The Secret keys are injected as environment variables into the Astromesh container.

### External Database

To use a managed PostgreSQL (e.g., AWS RDS) instead of the bundled subchart:

```yaml
postgresql:
  enabled: false

externalDatabase:
  host: "your-rds-instance.region.rds.amazonaws.com"
  port: "5432"
  database: astromesh
  username: astromesh
  existingSecret: astromesh-db-credentials  # must contain key DATABASE_PASSWORD
```

### External Redis

To use a managed Redis (e.g., AWS ElastiCache):

```yaml
redis:
  enabled: false

externalRedis:
  host: "your-elasticache.region.cache.amazonaws.com"
  port: "6379"
  existingSecret: astromesh-redis-credentials  # must contain key REDIS_PASSWORD
```

---

## Model Serving

### vLLM

Deploy an OpenAI-compatible vLLM server alongside Astromesh:

```yaml
vllm:
  enabled: true
  model: "mistralai/Mistral-7B-Instruct-v0.3"
  extraArgs:
    - "--max-model-len"
    - "4096"
  resources:
    requests:
      nvidia.com/gpu: "1"
    limits:
      nvidia.com/gpu: "1"
  nodeSelector:
    gpu: "true"
  huggingfaceToken: "hf_..."  # Required for gated models
```

The vLLM service is available at `<release>-astromesh-vllm:8000` within the cluster.

### HuggingFace TEI (Text Embeddings Inference)

Deploy one or more TEI instances for embeddings and reranking:

```yaml
tei:
  enabled: true
  instances:
    - name: embeddings
      modelId: "BAAI/bge-small-en-v1.5"
      port: 8002
      resources:
        limits:
          nvidia.com/gpu: "1"
      nodeSelector:
        gpu: "true"
    - name: reranker
      modelId: "BAAI/bge-reranker-base"
      port: 8003
  huggingfaceToken: "hf_..."  # If using gated models
```

Each instance creates a separate Deployment and Service: `<release>-astromesh-tei-embeddings`, `<release>-astromesh-tei-reranker`, etc.

### GPU Scheduling

Each GPU service (vLLM, Ollama, TEI) has independent `resources`, `nodeSelector`, and `tolerations` settings. Common GPU node configuration:

```yaml
nodeSelector:
  gpu: "true"
tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
resources:
  requests:
    nvidia.com/gpu: "1"
  limits:
    nvidia.com/gpu: "1"
```

---

## Observability

### Prometheus Annotations (always available)

The Astromesh Service includes Prometheus scrape annotations by default:

```yaml
observability:
  prometheus:
    enabled: true  # default
```

This adds `prometheus.io/scrape`, `prometheus.io/port`, and `prometheus.io/path` annotations.

### OpenTelemetry

**Manual endpoint:**
```yaml
observability:
  otel:
    enabled: true
    endpoint: "http://your-otel-collector:4317"
```

**Auto-wired with subchart:**
```yaml
opentelemetry-collector:
  enabled: true
```

When the OTel Collector subchart is enabled, the endpoint auto-resolves to the collector service. No manual configuration needed.

### Full Observability Stack (dedicated clusters)

For clusters dedicated to Astromesh, enable the full stack:

```yaml
observability:
  otel:
    enabled: true

kube-prometheus-stack:
  enabled: true
  grafana:
    adminPassword: your-password

opentelemetry-collector:
  enabled: true
```

This deploys Prometheus, Grafana, AlertManager, and the OTel Collector alongside Astromesh. The `values-dev.yaml` file enables all of this by default.

---

## Ingress

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: astromesh.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: astromesh-tls
      hosts:
        - astromesh.example.com
```

---

## Autoscaling

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

When HPA is enabled, the `replicaCount` value is ignored.

---

## Environment Profiles

Three pre-configured profiles are included:

### Development (`values-dev.yaml`)

```bash
helm install astromesh . -f values-dev.yaml
```

- 1 replica, low resources
- All subcharts enabled (PostgreSQL, Redis, Ollama, vLLM, TEI)
- Full observability stack enabled
- No Ingress, no TLS

### Staging (`values-staging.yaml`)

```bash
helm install astromesh . -f values-staging.yaml
```

- 2 replicas, HPA (2-4)
- Ingress with staging hostname
- Bundled databases
- No observability subcharts

### Production (`values-prod.yaml`)

```bash
helm install astromesh . -f values-prod.yaml
```

- 3 replicas, HPA (3-10)
- Ingress with TLS (cert-manager)
- External databases (RDS, ElastiCache)
- External secrets
- OTel enabled (assumes external collector)
- vLLM + TEI with GPU scheduling

---

## GitOps with ArgoCD

An ArgoCD `ApplicationSet` is provided for automated multi-environment deployment.

### Prerequisites

- ArgoCD installed in the cluster
- The Astromesh repository accessible from ArgoCD

### Deploy

```bash
kubectl apply -f deploy/gitops/argocd/applicationset.yaml
```

This creates three ArgoCD Applications:

| Application | Namespace | Values File | Auto-sync |
|-------------|-----------|-------------|-----------|
| `astromesh-dev` | astromesh-dev | values-dev.yaml | Yes |
| `astromesh-staging` | astromesh-staging | values-staging.yaml | Yes |
| `astromesh-prod` | astromesh-prod | values-prod.yaml | Yes |

All environments have:
- **Automated sync** with prune and self-heal
- **Automatic namespace creation**

### Workflow

1. Push changes to the repo (chart templates, values files, or config)
2. ArgoCD detects the change and syncs the affected environments
3. Rolling updates are triggered automatically when ConfigMaps change (via checksum annotations)

---

## Useful Commands

```bash
# Install
helm install astromesh deploy/helm/astromesh -f deploy/helm/astromesh/values-dev.yaml -n astromesh --create-namespace

# Upgrade
helm upgrade astromesh deploy/helm/astromesh -f deploy/helm/astromesh/values-dev.yaml -n astromesh

# Dry-run (preview rendered templates)
helm template astromesh deploy/helm/astromesh -f deploy/helm/astromesh/values-dev.yaml

# Lint
helm lint deploy/helm/astromesh
helm lint deploy/helm/astromesh -f deploy/helm/astromesh/values-prod.yaml

# Uninstall
helm uninstall astromesh -n astromesh

# Check status
helm status astromesh -n astromesh
kubectl get pods -n astromesh
```

---

## Future Phases

### Phase 5 — External Secrets
- External Secrets Operator integration
- AWS Secrets Manager / GCP Secret Manager / HashiCorp Vault support

### Phase 6 — Kubernetes Operator
- Custom CRDs: `Agent`, `Provider`, `Channel`, `RAGPipeline`
- Reconciliation logic for agent lifecycle management
- Auto-scaling based on agent workload metrics
