---
title: "Helm / Kubernetes"
description: "Production Kubernetes deployment with Helm chart"
---

This guide covers deploying Astromesh on Kubernetes using the official Helm chart. The chart packages the Astromesh runtime with optional PostgreSQL, Redis, Ollama, vLLM, HuggingFace TEI, and a full observability stack.

## What and Why

The Helm chart provides a production-grade Kubernetes deployment with:

- **Infrastructure as subcharts** -- PostgreSQL, Redis, and Ollama can be deployed alongside Astromesh or replaced with external managed services
- **Model serving** -- optional vLLM and HuggingFace TEI deployments with GPU scheduling
- **Observability** -- Prometheus, Grafana (via kube-prometheus-stack), and OpenTelemetry Collector
- **Configuration as code** -- Astromesh YAML config (runtime, providers, agents, channels) defined inline in `values.yaml`
- **Environment profiles** -- pre-built `values-dev.yaml`, `values-staging.yaml`, and `values-prod.yaml`
- **External Secrets** -- optional ESO integration for AWS, GCP, and Vault secret management
- **CRDs** -- Kubernetes-native Agent, Provider, Channel, and RAGPipeline resources

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Kubernetes | 1.26+ | `kubectl version` |
| Helm | 3.12+ | `helm version` |
| kubectl | configured | `kubectl cluster-info` |
| Container registry | accessible | varies |

## Chart Overview

### Structure

```
deploy/helm/astromesh/
├── Chart.yaml              # Chart metadata and dependencies
├── values.yaml             # Default configuration
├── values-dev.yaml         # Development overrides
├── values-staging.yaml     # Staging overrides
├── values-prod.yaml        # Production overrides
├── crds/                   # Custom Resource Definitions
│   ├── agent-crd.yaml
│   ├── provider-crd.yaml
│   ├── channel-crd.yaml
│   └── ragpipeline-crd.yaml
└── templates/
    ├── _helpers.tpl         # Template helpers
    ├── deployment.yaml      # Astromesh API deployment
    ├── service.yaml         # ClusterIP service
    ├── ingress.yaml         # Optional ingress
    ├── hpa.yaml             # Horizontal Pod Autoscaler
    ├── configmap-runtime.yaml
    ├── configmap-providers.yaml
    ├── configmap-channels.yaml
    ├── configmap-agents.yaml
    ├── secret.yaml
    ├── serviceaccount.yaml
    ├── deployment-vllm.yaml
    ├── service-vllm.yaml
    ├── deployment-tei.yaml
    ├── service-tei.yaml
    ├── external-secret.yaml
    ├── secret-store.yaml
    └── NOTES.txt
```

### Dependencies

| Subchart | Repository | Default | Purpose |
|----------|-----------|---------|---------|
| `postgresql` | Bitnami | enabled | Episodic memory, pgvector semantic search |
| `redis` | Bitnami | enabled | Conversational memory cache |
| `ollama` | ollama-helm | disabled | Local model serving |
| `kube-prometheus-stack` | prometheus-community | disabled | Prometheus + Grafana + AlertManager |
| `opentelemetry-collector` | open-telemetry | disabled | Trace and metric collection |

## Quick Start

### 1. Add dependency repositories and update

```bash
cd deploy/helm/astromesh
helm dependency update
```

Expected output:

```
Hang tight while we grab the latest from your chart repositories...
...Successfully got an update from the "bitnami" chart repository
Update Complete. ⎈Happy Helming!⎈
Saving 5 charts
Downloading postgresql from repo https://charts.bitnami.com/bitnami
Downloading redis from repo https://charts.bitnami.com/bitnami
Downloading ollama from repo https://otwld.github.io/ollama-helm
Deleting outdated charts
```

### 2. Install with dev values

```bash
helm install astromesh ./deploy/helm/astromesh \
  -f deploy/helm/astromesh/values-dev.yaml \
  --namespace astromesh \
  --create-namespace
```

Expected output:

```
NAME: astromesh
LAST DEPLOYED: Mon Mar  9 10:00:00 2026
NAMESPACE: astromesh
STATUS: deployed
REVISION: 1
NOTES:
Astromesh has been deployed!

  API endpoint: http://astromesh.astromesh.svc:8000
  Health check: kubectl port-forward svc/astromesh 8000:8000

To verify: curl http://localhost:8000/health
```

### 3. Verify pods

```bash
kubectl get pods -n astromesh
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
astromesh-5d8f9c7b6-x2k4m              1/1     Running   0          60s
astromesh-postgresql-0                  1/1     Running   0          60s
astromesh-redis-master-0                1/1     Running   0          60s
```

### 4. Test the API

```bash
kubectl port-forward svc/astromesh 8000:8000 -n astromesh
```

In another terminal:

```bash
curl http://localhost:8000/health
```

Expected output:

```json
{
  "status": "healthy",
  "version": "0.10.0"
}
```

## Configuration

### Inline config in values.yaml

Astromesh configuration files are defined inline in `values.yaml` and mounted as ConfigMaps:

```yaml
config:
  runtime: |
    apiVersion: astromesh/v1
    kind: RuntimeConfig
    metadata:
      name: default
    spec:
      api:
        host: "0.0.0.0"
        port: 8000
      defaults:
        orchestration:
          pattern: react
          max_iterations: 10

  providers: |
    apiVersion: astromesh/v1
    kind: ProviderConfig
    metadata:
      name: default-providers
    spec:
      providers:
        ollama:
          type: ollama
          endpoint: "http://ollama:11434"
          models:
            - "llama3.1:8b"
          health_check_interval: 30
        openai:
          type: openai_compat
          endpoint: "https://api.openai.com/v1"
          api_key_env: OPENAI_API_KEY
          models:
            - "gpt-4o"
            - "gpt-4o-mini"
      routing:
        default_strategy: cost_optimized
        fallback_enabled: true
        circuit_breaker:
          failure_threshold: 3
          recovery_timeout: 60

  channels: |
    channels:
      whatsapp:
        verify_token: "${WHATSAPP_VERIFY_TOKEN}"
        access_token: "${WHATSAPP_ACCESS_TOKEN}"
        phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
        app_secret: "${WHATSAPP_APP_SECRET}"
        default_agent: "whatsapp-assistant"

  agents:
    support-agent.agent.yaml: |
      apiVersion: astromesh/v1
      kind: Agent
      metadata:
        name: support-agent
      spec:
        identity:
          display_name: "Support Agent"
        model:
          primary:
            provider: ollama
            model: llama3.1:8b
        orchestration:
          pattern: react
          max_iterations: 5
```

Each section becomes a ConfigMap mounted at `/app/config/` inside the pod.

## Secrets

### Development: inline values

For development, set secret values directly in your values file:

```yaml
secrets:
  create: true
  values:
    OPENAI_API_KEY: "sk-dev-key-here"
    WHATSAPP_VERIFY_TOKEN: "dev-verify-token"
    WHATSAPP_ACCESS_TOKEN: "dev-access-token"
```

### Production: existing Secret

For production, create a Kubernetes Secret separately and reference it:

```bash
kubectl create secret generic astromesh-secrets \
  --from-literal=OPENAI_API_KEY="sk-prod-..." \
  --from-literal=WHATSAPP_ACCESS_TOKEN="EAAx..." \
  -n astromesh
```

Then in values:

```yaml
secrets:
  create: false
  existingSecret: "astromesh-secrets"
```

## External Database

To use an external PostgreSQL instance (e.g., AWS RDS) instead of the subchart:

```yaml
postgresql:
  enabled: false

externalDatabase:
  host: "your-rds-instance.region.rds.amazonaws.com"
  port: "5432"
  database: "astromesh"
  username: "astromesh"
  existingSecret: "astromesh-db-credentials"   # Secret with key DATABASE_PASSWORD
```

Create the credentials secret:

```bash
kubectl create secret generic astromesh-db-credentials \
  --from-literal=DATABASE_PASSWORD="your-rds-password" \
  -n astromesh
```

## External Redis

To use an external Redis instance (e.g., AWS ElastiCache):

```yaml
redis:
  enabled: false

externalRedis:
  host: "your-elasticache.region.cache.amazonaws.com"
  port: "6379"
  existingSecret: "astromesh-redis-credentials"  # Secret with key REDIS_PASSWORD
```

## Model Serving

### vLLM (GPU inference server)

Deploy vLLM for high-throughput, GPU-accelerated inference:

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
  tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule
```

If the model is gated (requires HuggingFace authentication):

```yaml
vllm:
  huggingfaceToken: "hf_..."
  # Or reference an existing secret:
  # existingSecret: "hf-token"
```

### HuggingFace TEI (embeddings and reranking)

Deploy Text Embeddings Inference for semantic search:

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
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule

    - name: reranker
      modelId: "BAAI/bge-reranker-base"
      port: 8003
      resources:
        limits:
          nvidia.com/gpu: "1"
      nodeSelector:
        gpu: "true"
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
```

Each `instances[]` entry creates a separate Deployment and Service.

## GPU Scheduling

GPU workloads (vLLM, TEI) need to be scheduled on nodes with GPUs. Configure per-service:

```yaml
vllm:
  nodeSelector:
    gpu: "true"                     # Only schedule on GPU-labeled nodes
  tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule            # Tolerate GPU node taints
  resources:
    requests:
      nvidia.com/gpu: "1"           # Request 1 GPU
    limits:
      nvidia.com/gpu: "1"           # Limit to 1 GPU
```

Label your GPU nodes:

```bash
kubectl label node gpu-node-1 gpu=true
```

Taint GPU nodes to prevent non-GPU workloads:

```bash
kubectl taint nodes gpu-node-1 nvidia.com/gpu=:NoSchedule
```

## Observability

### Prometheus annotations

Enabled by default. The Astromesh Service gets Prometheus scrape annotations:

```yaml
observability:
  prometheus:
    enabled: true   # Adds prometheus.io/scrape: "true" to Service
```

### OpenTelemetry (manual endpoint)

Point Astromesh to an existing OTel collector:

```yaml
observability:
  otel:
    enabled: true
    endpoint: "http://otel-collector.monitoring:4317"
```

### OpenTelemetry (subchart auto-wired)

Deploy an OTel Collector alongside Astromesh. The endpoint is auto-resolved:

```yaml
opentelemetry-collector:
  enabled: true
  mode: deployment
  config:
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318
    exporters:
      debug: {}
      prometheus:
        endpoint: 0.0.0.0:8889
    service:
      pipelines:
        traces:
          receivers: [otlp]
          exporters: [debug]
        metrics:
          receivers: [otlp]
          exporters: [prometheus]
```

### Full observability stack

Enable kube-prometheus-stack for Prometheus, Grafana, and AlertManager:

```yaml
kube-prometheus-stack:
  enabled: true
  prometheus:
    prometheusSpec:
      serviceMonitorSelectorNilUsesHelmValues: false
  grafana:
    adminPassword: admin

opentelemetry-collector:
  enabled: true

observability:
  prometheus:
    enabled: true
  otel:
    enabled: true
```

Access Grafana:

```bash
kubectl port-forward svc/astromesh-grafana 3000:80 -n astromesh
```

Open `http://localhost:3000` (admin/admin).

## Ingress

### nginx + cert-manager example

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
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

Verify:

```bash
kubectl get ingress -n astromesh
```

Expected output:

```
NAME        CLASS   HOSTS                    ADDRESS        PORTS     AGE
astromesh   nginx   astromesh.example.com    203.0.113.10   80, 443   5m
```

## Autoscaling

Enable the Horizontal Pod Autoscaler:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

Verify:

```bash
kubectl get hpa -n astromesh
```

Expected output:

```
NAME        REFERENCE              TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
astromesh   Deployment/astromesh   35%/70%   2         10        2          5m
```

## Environment Profiles

The chart ships with three environment profiles:

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| Replicas | 1 | 2 | 3 (HPA 3-10) |
| PostgreSQL | Subchart | Subchart | External (RDS) |
| Redis | Subchart | Subchart | External (ElastiCache) |
| Ollama | Subchart | -- | -- |
| vLLM | Enabled (no GPU limits) | Enabled (GPU) | Enabled (GPU) |
| TEI | Embeddings only | Embeddings | Embeddings + Reranker |
| Observability | Full stack (subcharts) | OTel only | OTel to external |
| Ingress | Disabled | Enabled | Enabled + TLS |
| Secrets | Inline | Inline | existingSecret |
| Resources | 250m/512Mi | 500m/1Gi | 1/2Gi - 4/4Gi |

Install with a specific profile:

```bash
# Development
helm install astromesh ./deploy/helm/astromesh -f deploy/helm/astromesh/values-dev.yaml -n astromesh-dev --create-namespace

# Staging
helm install astromesh ./deploy/helm/astromesh -f deploy/helm/astromesh/values-staging.yaml -n astromesh-staging --create-namespace

# Production
helm install astromesh ./deploy/helm/astromesh -f deploy/helm/astromesh/values-prod.yaml -n astromesh-prod --create-namespace
```

## External Secrets (ESO)

For production secret management, use the External Secrets Operator to sync secrets from AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault.

**Prerequisite:** ESO must be installed in your cluster. It is a cluster-level operator, not deployed per-application.

### SecretStore setup

```yaml
externalSecrets:
  enabled: true
  refreshInterval: 1h
  secretStore:
    enabled: true
    kind: SecretStore
    provider:
      aws:
        service: SecretsManager
        region: us-east-1
        auth:
          secretRef:
            accessKeyIDSecretRef:
              name: aws-credentials
              key: access-key-id
            secretAccessKeySecretRef:
              name: aws-credentials
              key: secret-access-key
```

### ExternalSecret keys

```yaml
externalSecrets:
  keys:
    - secretKey: OPENAI_API_KEY
      remoteRef:
        key: astromesh/openai
        property: api_key
    - secretKey: WHATSAPP_ACCESS_TOKEN
      remoteRef:
        key: astromesh/whatsapp
        property: access_token
    - secretKey: DATABASE_PASSWORD
      remoteRef:
        key: astromesh/database
        property: password
```

When `externalSecrets.enabled=true`, the ExternalSecret resource creates a Kubernetes Secret with the same name as the Astromesh release. Set `secrets.create: false` to avoid conflicts with the inline secret.

### Provider examples

**AWS Secrets Manager:**

```yaml
provider:
  aws:
    service: SecretsManager
    region: us-east-1
    auth:
      secretRef:
        accessKeyIDSecretRef:
          name: aws-credentials
          key: access-key-id
        secretAccessKeySecretRef:
          name: aws-credentials
          key: secret-access-key
```

**GCP Secret Manager:**

```yaml
provider:
  gcpsm:
    projectID: my-gcp-project
    auth:
      secretRef:
        secretAccessKeySecretRef:
          name: gcp-credentials
          key: secret-access-credentials
```

**HashiCorp Vault:**

```yaml
provider:
  vault:
    server: https://vault.example.com
    path: secret
    version: v2
    auth:
      kubernetes:
        mountPath: kubernetes
        role: astromesh
```

## CRDs

The chart installs four Custom Resource Definitions for Kubernetes-native agent management:

| CRD | Group | Kind | Scope |
|-----|-------|------|-------|
| `agents.astromesh.io` | astromesh.io | Agent | Namespaced |
| `providers.astromesh.io` | astromesh.io | Provider | Namespaced |
| `channels.astromesh.io` | astromesh.io | Channel | Namespaced |
| `ragpipelines.astromesh.io` | astromesh.io | RAGPipeline | Namespaced |

All CRDs use API version `v1alpha1` with a status subresource.

### Create an Agent via kubectl

```bash
kubectl apply -f - <<EOF
apiVersion: astromesh.io/v1alpha1
kind: Agent
metadata:
  name: support-agent
  namespace: astromesh
spec:
  identity:
    display_name: "Support Agent"
    description: "Handles customer support queries"
  model:
    primary:
      provider: ollama
      model: llama3.1:8b
  orchestration:
    pattern: react
    max_iterations: 5
EOF
```

Expected output:

```
agent.astromesh.io/support-agent created
```

### List agents

```bash
kubectl get agents -n astromesh
```

Expected output:

```
NAME            AGE
support-agent   10s
```

### Create a Provider

```bash
kubectl apply -f - <<EOF
apiVersion: astromesh.io/v1alpha1
kind: Provider
metadata:
  name: openai
  namespace: astromesh
spec:
  type: openai_compat
  endpoint: "https://api.openai.com/v1"
  api_key_env: OPENAI_API_KEY
  models:
    - gpt-4o
    - gpt-4o-mini
EOF
```

### Create a Channel

```bash
kubectl apply -f - <<EOF
apiVersion: astromesh.io/v1alpha1
kind: Channel
metadata:
  name: whatsapp
  namespace: astromesh
spec:
  type: whatsapp
  default_agent: support-agent
  rate_limit:
    window_seconds: 60
    max_messages: 30
EOF
```

### Create a RAGPipeline

```bash
kubectl apply -f - <<EOF
apiVersion: astromesh.io/v1alpha1
kind: RAGPipeline
metadata:
  name: docs-search
  namespace: astromesh
spec:
  embeddings:
    provider: tei
    endpoint: "http://astromesh-tei-embeddings:8002"
  vector_store:
    type: pgvector
  chunking:
    strategy: recursive
    chunk_size: 512
    overlap: 50
EOF
```

**Note:** CRD definitions are installed with the chart, but the reconciliation controller is a separate project. Currently, CRDs serve as documentation of intent and can be used by external automation.

## Useful Commands

### Install

```bash
helm install astromesh ./deploy/helm/astromesh \
  -f deploy/helm/astromesh/values-dev.yaml \
  -n astromesh --create-namespace
```

### Upgrade

```bash
helm upgrade astromesh ./deploy/helm/astromesh \
  -f deploy/helm/astromesh/values-prod.yaml \
  -n astromesh
```

### Dry run (preview changes)

```bash
helm upgrade astromesh ./deploy/helm/astromesh \
  -f deploy/helm/astromesh/values-prod.yaml \
  -n astromesh --dry-run --debug
```

### Template rendering (no cluster needed)

```bash
helm template astromesh ./deploy/helm/astromesh \
  -f deploy/helm/astromesh/values-dev.yaml
```

### Lint

```bash
helm lint ./deploy/helm/astromesh \
  -f deploy/helm/astromesh/values-prod.yaml
```

Expected output:

```
==> Linting ./deploy/helm/astromesh
[INFO] Chart.yaml: icon is recommended

1 chart(s) linted, 0 chart(s) failed
```

### Uninstall

```bash
helm uninstall astromesh -n astromesh
```

**Note:** CRDs are not removed on uninstall (Helm convention). Remove manually if needed:

```bash
kubectl delete crd agents.astromesh.io providers.astromesh.io channels.astromesh.io ragpipelines.astromesh.io
```

### View installed values

```bash
helm get values astromesh -n astromesh
```

### View all resources

```bash
kubectl get all -n astromesh
```

Expected output:

```
NAME                             READY   STATUS    RESTARTS   AGE
pod/astromesh-5d8f9c7b6-x2k4m   1/1     Running   0          5m
pod/astromesh-postgresql-0       1/1     Running   0          5m
pod/astromesh-redis-master-0     1/1     Running   0          5m

NAME                              TYPE        CLUSTER-IP      PORT(S)
service/astromesh                 ClusterIP   10.96.100.1     8000/TCP
service/astromesh-postgresql      ClusterIP   10.96.100.2     5432/TCP
service/astromesh-redis-master    ClusterIP   10.96.100.3     6379/TCP

NAME                        READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/astromesh   1/1     1            1           5m
```

## Production Checklist

Before going to production, verify the following:

- [ ] **Secrets:** Using `existingSecret` or External Secrets, not inline values
- [ ] **Database:** External managed PostgreSQL (RDS, Cloud SQL) with backups
- [ ] **Redis:** External managed Redis (ElastiCache, Memorystore) or Redis with persistence
- [ ] **Ingress:** TLS enabled with valid certificate (cert-manager or manual)
- [ ] **Resources:** CPU and memory requests/limits set for all workloads
- [ ] **Autoscaling:** HPA enabled with appropriate min/max replicas
- [ ] **Observability:** OTel tracing and Prometheus metrics enabled
- [ ] **GPU:** nodeSelector and tolerations set for GPU workloads
- [ ] **Network policies:** Restrict traffic between namespaces if required
- [ ] **RBAC:** ServiceAccount with minimal permissions
- [ ] **Image:** Using a specific image tag, not `latest`
- [ ] **Backups:** Database backup schedule configured
