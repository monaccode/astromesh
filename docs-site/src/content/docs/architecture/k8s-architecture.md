---
title: Kubernetes-Style Architecture
description: CRDs, operator design, and Kubernetes-native resource model
---

Astromesh's configuration system is modeled after Kubernetes. Every resource -- agents, providers, RAG pipelines, runtime settings -- follows the same declarative schema pattern: `apiVersion`, `kind`, `metadata`, `spec`. This page describes the Custom Resource Definitions (CRDs) that will allow Astromesh to run as a Kubernetes-native operator, and how the current YAML configuration maps to these CRDs.

## Resource Model

All Astromesh resources share a common structure inspired by Kubernetes:

```yaml
apiVersion: astromesh.io/v1alpha1   # API group and version
kind: Agent                         # Resource type
metadata:
  name: support-agent               # Unique identifier
  namespace: default                # Kubernetes namespace
  labels:                           # Key-value labels for filtering
    team: customer-support
    environment: production
  annotations:                      # Non-identifying metadata
    astromesh.io/description: "Customer support agent"
spec:
  # Resource-specific configuration
  ...
status:
  # Controller-managed state (read-only for users)
  ...
```

This structure provides several benefits:

- **Familiar interface** -- Teams already using Kubernetes can manage Astromesh resources with the same tools and patterns (`kubectl`, GitOps, RBAC).
- **Declarative management** -- You describe the desired state, and the controller reconciles it.
- **Label-based selection** -- Resources can be filtered, grouped, and selected using label selectors.
- **Status subresource** -- The controller reports the observed state (health, readiness, conditions) separately from the desired spec.

### Current YAML vs. CRDs

Today, Astromesh uses local YAML files with `apiVersion: astromesh/v1` (no API group). The CRD definitions use `apiVersion: astromesh.io/v1alpha1` to follow Kubernetes API group conventions. The mapping is straightforward:

| Current Config | CRD Kind | Config Location |
|---------------|----------|-----------------|
| `kind: Agent` | `Agent` | `config/agents/*.agent.yaml` |
| `kind: ProviderConfig` | `Provider` | `config/providers.yaml` |
| Channel settings | `Channel` | `config/channels.yaml` |
| `kind: RAGPipeline` | `RAGPipeline` | `config/rag/*.rag.yaml` |

When running outside Kubernetes, the existing YAML files work unchanged. When running inside Kubernetes with the Astromesh operator, the same configuration is expressed as CRDs and managed by `kubectl` and standard Kubernetes tooling.

---

## CRD: Agent

The Agent CRD defines an intelligent agent with its model configuration, orchestration pattern, tools, memory, and guardrails.

### Definition

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: agents.astromesh.io
spec:
  group: astromesh.io
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                identity:
                  type: object
                  properties:
                    display_name:
                      type: string
                    description:
                      type: string
                model:
                  type: object
                  properties:
                    primary:
                      type: object
                      properties:
                        provider:
                          type: string
                        model:
                          type: string
                        endpoint:
                          type: string
                        parameters:
                          type: object
                          x-kubernetes-preserve-unknown-fields: true
                    fallback:
                      type: array
                      items:
                        type: object
                        x-kubernetes-preserve-unknown-fields: true
                    routing:
                      type: object
                      properties:
                        strategy:
                          type: string
                          enum: [cost_optimized, latency_optimized, quality_first, round_robin, capability_match]
                orchestration:
                  type: object
                  properties:
                    pattern:
                      type: string
                      enum: [react, plan_and_execute, parallel_fan_out, pipeline, supervisor, swarm]
                    max_iterations:
                      type: integer
                    timeout_seconds:
                      type: integer
                prompts:
                  type: object
                  properties:
                    system:
                      type: string
                tools:
                  type: array
                  items:
                    type: object
                    x-kubernetes-preserve-unknown-fields: true
                memory:
                  type: object
                  x-kubernetes-preserve-unknown-fields: true
                guardrails:
                  type: object
                  x-kubernetes-preserve-unknown-fields: true
            status:
              type: object
              properties:
                phase:
                  type: string
                ready:
                  type: boolean
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
                      status:
                        type: string
                      lastTransitionTime:
                        type: string
                      reason:
                        type: string
                      message:
                        type: string
      subresources:
        status: {}
      additionalPrinterColumns:
        - name: Display Name
          type: string
          jsonPath: .spec.identity.display_name
        - name: Provider
          type: string
          jsonPath: .spec.model.primary.provider
        - name: Model
          type: string
          jsonPath: .spec.model.primary.model
        - name: Pattern
          type: string
          jsonPath: .spec.orchestration.pattern
        - name: Ready
          type: boolean
          jsonPath: .status.ready
        - name: Age
          type: date
          jsonPath: .metadata.creationTimestamp
  scope: Namespaced
  names:
    plural: agents
    singular: agent
    kind: Agent
    shortNames:
      - ag
```

### Example Resource

```yaml
apiVersion: astromesh.io/v1alpha1
kind: Agent
metadata:
  name: support-agent
  namespace: production
  labels:
    team: customer-support
    tier: frontend
spec:
  identity:
    display_name: "Customer Support Agent"
    description: "Handles customer inquiries about products, orders, and returns"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://ollama.inference.svc:11434"
      parameters:
        temperature: 0.7
        max_tokens: 2048
    fallback:
      - provider: openai-compat
        model: "gpt-4o-mini"
        endpoint: "https://api.openai.com/v1"
        parameters:
          temperature: 0.7
    routing:
      strategy: cost_optimized

  orchestration:
    pattern: react
    max_iterations: 10
    timeout_seconds: 120

  prompts:
    system: |
      You are a customer support agent for Acme Corp.
      Be helpful, concise, and professional.
      {% if semantic_context %}
      Relevant knowledge base articles:
      {{ semantic_context }}
      {% endif %}

  tools:
    - name: search_knowledge_base
      type: rag
      pipeline: support-kb
    - name: create_ticket
      type: webhook
      endpoint: "http://ticketing.internal.svc/api/tickets"
      method: POST

  memory:
    conversational:
      backend: redis
      strategy: sliding_window
      window_size: 20
    semantic:
      backend: pgvector
      collection: support-knowledge

  guardrails:
    input:
      - type: pii_detection
        action: redact
      - type: max_length
        max_characters: 5000
    output:
      - type: content_filter
        forbidden_keywords: ["internal_only"]
        action: redact
      - type: cost_limit
        max_tokens_per_turn: 4000
```

### kubectl Output

```
$ kubectl get agents -n production
NAME            DISPLAY NAME              PROVIDER   MODEL          PATTERN   READY   AGE
support-agent   Customer Support Agent    ollama     llama3.1:8b    react     true    3d
sales-agent     Sales Assistant           openai     gpt-4o-mini    react     true    1d
analyst-agent   Data Analyst              vllm       mistral-7b     plan      false   2h
```

### Status Conditions

The Agent controller maintains the following conditions:

| Condition | Description |
|-----------|-------------|
| `ProviderReachable` | The primary LLM provider is responding to health checks |
| `MemoryConnected` | All configured memory backends are connected |
| `ToolsRegistered` | All configured tools have been discovered and registered |
| `GuardrailsLoaded` | All guardrail rules have been parsed and loaded |
| `Ready` | All conditions above are true; the agent is ready to serve requests |

---

## CRD: Provider

The Provider CRD defines an LLM provider endpoint and its capabilities.

### Example Resource

```yaml
apiVersion: astromesh.io/v1alpha1
kind: Provider
metadata:
  name: ollama-local
  namespace: inference
  labels:
    backend: ollama
    tier: local
spec:
  type: ollama
  endpoint: "http://ollama.inference.svc:11434"
  models:
    - name: "llama3.1:8b"
      capabilities:
        tools: true
        vision: false
      quality_score: 0.85
      cost_per_1k_tokens: 0.0
    - name: "llama3.1:70b"
      capabilities:
        tools: true
        vision: false
      quality_score: 0.95
      cost_per_1k_tokens: 0.0
  healthCheck:
    interval: 30s
    timeout: 5s
    path: /api/tags
  circuitBreaker:
    failureThreshold: 3
    cooldownSeconds: 60
```

### kubectl Output

```
$ kubectl get providers -n inference
NAME             TYPE      ENDPOINT                                MODELS   HEALTHY   AGE
ollama-local     ollama    http://ollama.inference.svc:11434       2        true      5d
openai-cloud     openai    https://api.openai.com/v1               3        true      5d
vllm-gpu         vllm      http://vllm.inference.svc:8000          1        true      2d
```

### Status Conditions

| Condition | Description |
|-----------|-------------|
| `EndpointReachable` | The provider endpoint is responding to health checks |
| `ModelsAvailable` | At least one configured model is available for inference |
| `CircuitClosed` | The circuit breaker is in closed (healthy) state |

---

## CRD: Channel

The Channel CRD defines an external messaging platform integration.

### Example Resource

```yaml
apiVersion: astromesh.io/v1alpha1
kind: Channel
metadata:
  name: whatsapp-support
  namespace: production
  labels:
    platform: whatsapp
    team: customer-support
spec:
  type: whatsapp
  defaultAgent: support-agent
  webhook:
    path: /v1/channels/whatsapp/webhook
    verifyToken:
      secretKeyRef:
        name: whatsapp-credentials
        key: verify-token
  credentials:
    appSecret:
      secretKeyRef:
        name: whatsapp-credentials
        key: app-secret
    accessToken:
      secretKeyRef:
        name: whatsapp-credentials
        key: access-token
    phoneNumberId:
      secretKeyRef:
        name: whatsapp-credentials
        key: phone-number-id
  rateLimiting:
    maxRequestsPerSecond: 10
    maxRequestsPerMinute: 100
```

### kubectl Output

```
$ kubectl get channels -n production
NAME                TYPE       DEFAULT AGENT    CONNECTED   AGE
whatsapp-support    whatsapp   support-agent    true        7d
slack-engineering   slack      eng-agent        true        3d
```

### Status Conditions

| Condition | Description |
|-----------|-------------|
| `WebhookVerified` | The platform has verified the webhook endpoint |
| `CredentialsValid` | API credentials are valid and not expired |
| `AgentAvailable` | The default agent exists and is in Ready state |

---

## CRD: RAGPipeline

The RAGPipeline CRD defines a retrieval-augmented generation pipeline with chunking, embedding, storage, and reranking configuration.

### Example Resource

```yaml
apiVersion: astromesh.io/v1alpha1
kind: RAGPipeline
metadata:
  name: support-kb
  namespace: production
  labels:
    domain: customer-support
spec:
  chunking:
    strategy: recursive
    chunkSize: 512
    chunkOverlap: 50
    separators: ["\n\n", "\n", ". ", " "]

  embedding:
    provider: sentence-transformers
    model: "all-MiniLM-L6-v2"
    dimensions: 384
    # Or use a remote embedding service:
    # provider: huggingface-api
    # endpoint: "http://embeddings.inference.svc:8002"

  store:
    backend: pgvector
    connection:
      secretKeyRef:
        name: postgres-credentials
        key: connection-string
    collection: support-knowledge
    distanceMetric: cosine

  reranking:
    enabled: true
    model: cross-encoder
    topK: 5
    # Or use Cohere:
    # model: cohere
    # apiKey:
    #   secretKeyRef:
    #     name: cohere-credentials
    #     key: api-key

  ingestion:
    sources:
      - type: directory
        path: /data/knowledge-base/
        glob: "**/*.md"
      - type: url
        urls:
          - "https://docs.example.com/faq"
    schedule: "0 2 * * *"  # Nightly re-ingestion
```

### kubectl Output

```
$ kubectl get ragpipelines -n production
NAME          STORE      EMBEDDING MODEL      DOCUMENTS   CHUNKS    LAST INGESTED   AGE
support-kb    pgvector   all-MiniLM-L6-v2     142         3,847     2h ago          14d
product-docs  qdrant     all-MiniLM-L6-v2     89          2,103     6h ago          7d
```

### Status Conditions

| Condition | Description |
|-----------|-------------|
| `StoreConnected` | The vector store backend is reachable |
| `EmbeddingModelLoaded` | The embedding model is loaded and ready |
| `IngestionComplete` | The most recent ingestion run completed successfully |
| `IndexHealthy` | The vector index is consistent and queryable |

---

## Operator Controller Design

The Astromesh operator follows the standard Kubernetes controller pattern: watch for resource changes, compare desired state to observed state, and reconcile.

### Controller Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Astromesh Operator                       │
│                                                             │
│  ┌───────────────────┐  ┌───────────────────┐               │
│  │  Agent Controller │  │Provider Controller│               │
│  │                   │  │                   │               │
│  │ Watch: Agent CRs  │  │ Watch: Provider   │               │
│  │ Reconcile:        │  │ Reconcile:        │               │
│  │  - Bootstrap agent│  │  - Health check   │               │
│  │  - Wire deps      │  │  - Update status  │               │
│  │  - Update status  │  │  - Circuit breaker│               │
│  └───────────────────┘  └───────────────────┘               │
│                                                             │
│  ┌───────────────────┐ ┌───────────────────┐                │
│  │Channel Controller │ │  RAG Controller   │                │
│  │                   │ │                   │                │
│  │ Watch: Channel CRs│ │ Watch: RAGPipeline│                │
│  │ Reconcile:        │ │ Reconcile:        │                │
│  │ - Register        │ │                   │                │
│  │    webhook        │ │  - Connect store  │                │
│  │ - Validate creds  │ │  - Run ingestion  │                │
│  │ - Link agent      │ │  - Update index   │                │
│  └───────────────────┘ └───────────────────┘                │
│                                                             │
│  ┌─────────────────────────────────────────┐                │
│  │           Shared Components             │                │
│  │  - AgentRuntime (in-process)            │                │
│  │  - Metrics exporter (Prometheus)        │                │
│  │  - Leader election                      │                │
│  │  - Webhook admission controller         │                │
│  └─────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

### Reconciliation Loop

Each controller follows the same reconciliation pattern:

1. **Watch** -- The controller watches its CRD for create, update, and delete events.
2. **Fetch** -- On event, fetch the current resource spec and status.
3. **Compare** -- Compare the desired state (spec) with the observed state (status).
4. **Act** -- If they differ, take action to bring observed state in line with desired state.
5. **Update status** -- Write the new observed state back to the status subresource.

For example, the Agent Controller reconciliation:

```
Event: Agent "support-agent" created
  │
  ├── Parse spec
  ├── Resolve provider references → check Provider CRs exist and are Ready
  ├── Resolve tool references → check Tool configs are valid
  ├── Bootstrap Agent instance in runtime
  ├── Run health checks (provider reachable, memory connected, tools registered)
  └── Update status:
      ├── phase: Running
      ├── ready: true
      └── conditions:
          ├── ProviderReachable: True
          ├── MemoryConnected: True
          ├── ToolsRegistered: True
          ├── GuardrailsLoaded: True
          └── Ready: True
```

### Webhook Admission Controller

A validating webhook catches invalid configurations before they are persisted to etcd:

- **Agent validation** -- Verifies that referenced providers exist, orchestration pattern is valid, tool names are registered, and memory backend configuration is correct.
- **Provider validation** -- Verifies that the endpoint URL is well-formed and the provider type is supported.
- **RAGPipeline validation** -- Verifies that the embedding dimensions match the vector store configuration and that the chunking parameters are valid.

---

## Control Plane vs. Data Plane

The Astromesh architecture separates the control plane (configuration, lifecycle, policy) from the data plane (request processing, inference, storage).

```
┌─────────────────────────────────────────────────────────────────┐
│                         CONTROL PLANE                           │
│                                                                 │
│  Kubernetes API Server                                          │
│  ├── Agent CRDs          ← Desired state                        │
│  ├── Provider CRDs       ← Provider registry                    │
│  ├── Channel CRDs        ← Channel config                       │
│  └── RAGPipeline CRDs    ← Knowledge config                     │
│                                                                 │
│  Astromesh Operator                                             │
│  ├── Controllers         ← Watch + reconcile                    │
│  ├── Admission webhooks  ← Validate before persist              │
│  └── Leader election     ← HA active-passive                    │
│                                                                 │
│  Policies                                                       │
│  ├── Routing strategies  ← How to select providers              │
│  ├── Guardrail rules     ← Safety policies                      │
│  ├── Tool permissions    ← Access control                       │
│  └── Cost budgets        ← Spending limits                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                    Reconciliation loop
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          DATA PLANE                             │
│                                                                 │
│  Agent Runtime Pods                                             │
│  ├── FastAPI server      ← HTTP/WS request handling             │
│  ├── Agent instances     ← Bootstrapped from CRDs               │
│  ├── Model Router        ← Provider selection + circuit breaker │
│  └── Orchestration       ← ReAct / Plan / Supervisor loops      │
│                                                                 │
│  Inference Services                                             │
│  ├── Ollama pods         ← Local LLM inference                  │
│  ├── vLLM pods           ← High-throughput GPU inference        │
│  └── Embedding pods      ← Text embedding service               │
│                                                                 │
│  Storage Services                                               │
│  ├── PostgreSQL + pgvector  ← Relational + vector storage       │
│  ├── Redis                  ← Conversation cache                │
│  └── Qdrant / ChromaDB     ← Dedicated vector stores            │
│                                                                 │
│  Observability                                                  │
│  ├── OpenTelemetry Collector ← Trace collection                 │
│  ├── Prometheus              ← Metrics scraping                 │
│  └── Grafana                 ← Dashboards                       │
└─────────────────────────────────────────────────────────────────┘
```

### Key separation benefits

**Control plane** manages what should exist and how it should behave. Changes here (editing an Agent CRD, updating a Provider endpoint) trigger reconciliation but do not directly handle user traffic.

**Data plane** handles the actual agent requests, LLM inference, tool execution, and storage operations. It is configured by the control plane but operates independently for each request.

This separation means you can:

- **Scale the data plane independently** -- Add more Agent Runtime pods to handle more concurrent requests without changing control plane configuration.
- **Update configuration without downtime** -- Editing an Agent CRD triggers a rolling reconciliation that updates the agent in-place without dropping active connections.
- **Use GitOps** -- Store all CRDs in Git, use ArgoCD or Flux to automatically apply changes, and get full audit trails of every configuration change.
- **Apply RBAC** -- Use Kubernetes RBAC to control who can create/modify agents, providers, and channels. Teams can manage their own agents within their namespace.

---

## What's Next

- **[Architecture Overview](/astromesh/architecture/overview/)** -- High-level view of how all components fit together.
- **[Four-Layer Design](/astromesh/architecture/four-layer-design/)** -- Detailed walkthrough of each architectural layer in the current (non-Kubernetes) runtime.
- **[Agent Execution Pipeline](/astromesh/architecture/agent-pipeline/)** -- Step-by-step request flow through the data plane.
