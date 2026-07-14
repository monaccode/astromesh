# Astromesh Orbit — Configuration Reference

Complete reference for `orbit.yaml`, the declarative configuration file that defines your Astromesh cloud deployment.

---

## File Format

```yaml
apiVersion: astromesh/v1
kind: OrbitDeployment
metadata:
  name: <string>
  environment: <string>

spec:
  provider: { ... }
  compute: { ... }
  database: { ... }
  cache: { ... }
  secrets: { ... }
  images: { ... }
```

Orbit uses Pydantic for validation. Invalid configurations fail fast with clear error messages before any Terraform operation.

---

## Top-Level Fields

### `apiVersion`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Yes |
| **Value** | `astromesh/v1` |

Must be `astromesh/v1`. Reserved for future schema versions.

---

### `kind`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Yes |
| **Value** | `OrbitDeployment` |

Must be `OrbitDeployment`.

---

## `metadata`

### `metadata.name`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Yes |
| **Pattern** | `^[a-z][a-z0-9-]{1,30}[a-z0-9]$` |
| **Example** | `my-astromesh` |

Deployment name. Used as a prefix for all provisioned resources (e.g., `my-astromesh-runtime`, `my-astromesh-db`). Must be lowercase, alphanumeric with hyphens, 3-32 characters.

---

### `metadata.environment`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `production` |
| **Allowed** | `dev`, `staging`, `production` |

Environment label. Affects resource naming (appended as suffix) and default behaviors:

| Environment | Effect |
|---|---|
| `dev` | Allows `min_instances: 0` everywhere, smaller default resources |
| `staging` | Same as production defaults but with environment suffix in names |
| `production` | Full defaults, enforces `min_instances >= 1` for runtime |

---

## `spec.provider`

Cloud provider configuration.

### `spec.provider.name`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Yes |
| **Allowed** | `gcp` (MVP). `aws`, `azure` planned for v1.0. |

Determines which provider plugin is loaded and which templates are used.

---

### `spec.provider.project`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Yes (GCP) |
| **Example** | `my-gcp-project-id` |

GCP project ID. Must exist and the authenticated user must have `roles/owner` or `roles/editor`.

---

### `spec.provider.region`

| | |
|---|---|
| **Type** | `string` |
| **Required** | Yes |
| **Default** | `us-central1` |
| **Example** | `europe-west1`, `asia-northeast1` |

Cloud region for all resources. All services are deployed to the same region.

---

## `spec.compute`

Compute resources for the Astromesh runtime. It is deployed as a single Cloud Run service (GCP).

### Service Blocks

One service block:

- `spec.compute.runtime` — Astromesh core runtime (AgentRuntime + ModelRouter + ToolRegistry)

### `spec.compute.runtime.min_instances`

| | |
|---|---|
| **Type** | `integer` |
| **Required** | No |
| **Default** | `1` |
| **Range** | `0` - `100` |

Minimum number of running instances. Setting to `0` enables scale-to-zero (cold starts apply). In `production` environment, runtime enforces a minimum of `1`.

---

### `spec.compute.runtime.max_instances`

| | |
|---|---|
| **Type** | `integer` |
| **Required** | No |
| **Default** | `5` |
| **Range** | `1` - `100` |

Maximum number of instances for auto-scaling. Must be >= `min_instances`.

---

### `spec.compute.runtime.cpu`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `"2"` |
| **Allowed** | `"1"`, `"2"`, `"4"`, `"8"` |

CPU allocation per instance. Cloud Run supports up to 8 vCPUs per instance.

---

### `spec.compute.runtime.memory`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `"2Gi"` |
| **Pattern** | `^[0-9]+(Mi|Gi)$` |

Memory allocation per instance. Must be compatible with the CPU setting — Cloud Run enforces minimum memory-to-CPU ratios.

---

## `spec.database`

PostgreSQL database configuration. Maps to Cloud SQL for PostgreSQL on GCP.

### `spec.database.tier`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `db-f1-micro` |

Cloud SQL machine tier. Common values:

| Tier | vCPU | RAM | Use case |
|---|---|---|---|
| `db-f1-micro` | shared | 0.6 GB | Dev, starter |
| `db-g1-small` | shared | 1.7 GB | Small production |
| `db-custom-1-3840` | 1 | 3.75 GB | Medium production |
| `db-custom-2-7680` | 2 | 7.5 GB | Large production |

---

### `spec.database.version`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `POSTGRES_16` |
| **Allowed** | `POSTGRES_14`, `POSTGRES_15`, `POSTGRES_16` |

PostgreSQL major version.

---

### `spec.database.storage_gb`

| | |
|---|---|
| **Type** | `integer` |
| **Required** | No |
| **Default** | `10` |
| **Range** | `10` - `65536` |

Disk size in GB. Cloud SQL supports automatic storage increase — this is the initial allocation.

---

### `spec.database.high_availability`

| | |
|---|---|
| **Type** | `boolean` |
| **Required** | No |
| **Default** | `false` |

Enable regional high availability (standby replica in a different zone). Doubles the database cost. Recommended for production workloads.

---

## `spec.cache`

Redis cache configuration. Maps to Memorystore for Redis on GCP.

### `spec.cache.tier`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `basic` |
| **Allowed** | `basic`, `standard` |

| Tier | Description |
|---|---|
| `basic` | Single node, no replication. Suitable for dev and small workloads. |
| `standard` | Replica in a different zone. Automatic failover. Recommended for production. |

---

### `spec.cache.memory_gb`

| | |
|---|---|
| **Type** | `integer` |
| **Required** | No |
| **Default** | `1` |
| **Range** | `1` - `300` |

Redis memory size in GB.

---

## `spec.secrets`

Secret Manager configuration. Orbit creates the secret entries; the user populates them.

### `spec.secrets.provider_keys`

| | |
|---|---|
| **Type** | `boolean` |
| **Required** | No |
| **Default** | `true` |

Create an empty Secret Manager entry for LLM provider API keys. After deploy, populate it via the GCP Console or:

```bash
echo -n "sk-your-key" | gcloud secrets versions add astromesh-provider-keys --data-file=-
```

---

### `spec.secrets.jwt_secret`

| | |
|---|---|
| **Type** | `boolean` |
| **Required** | No |
| **Default** | `true` |

Create a Secret Manager entry for the JWT signing secret. An auto-generated random value is stored on first deploy. Subsequent deploys reuse the existing secret.

---

## `spec.images`

Container image reference for the runtime service. Override this to use a custom image or pin a specific version.

### `spec.images.runtime`

| | |
|---|---|
| **Type** | `string` |
| **Required** | No |
| **Default** | `fulfarodev/astromesh:latest` |

Container image for the Astromesh core runtime.

---

## `spec.storage`

Optional. Both blocks default to `enabled: true`.

```yaml
spec:
  storage:
    rag_documents:
      enabled: true       # provision the GCS RAG documents bucket
      versioning: true    # keep object versions
    artifact_registry:
      enabled: true       # provision a Docker Artifact Registry repo
      repository: ""      # empty -> "<metadata.name>-images"
```

Using pgvector on the deployed Cloud SQL as the RAG vector store:

```yaml
kind: RAGPipeline
metadata: { name: docs }
spec:
  embeddings: { provider: sentence_transformers, model: all-MiniLM-L6-v2, dimension: 384 }
  vector_store:
    backend: pgvector
    collection: embeddings
    connection:
      host: /cloudsql/<CONNECTION_NAME>
      user: astromesh
      database: astromesh
```

---

## `spec.observability`

Optional.

```yaml
spec:
  observability:
    dashboard: true              # Cloud Monitoring dashboard (default: true)
    tracing:
      enabled: false             # OTel Collector sidecar -> Cloud Trace (default: false)
      collector_image: "otel/opentelemetry-collector-contrib:0.115.1"
```

`tracing` is off by default because the sidecar adds a container to every Cloud Run instance.
Enabling it also sets `ASTROMESH_OTLP_ENABLED=1` on the runtime container, which is what makes
the astromesh runtime export spans.

There is no `logging` field: Cloud Run ships container logs to Cloud Logging automatically.

---

## Wizard Presets

The `orbit init` wizard offers two presets that populate `orbit.yaml` with explicit values.

### Starter (~$15/mo)

```yaml
spec:
  compute:
    runtime:
      min_instances: 1
      max_instances: 1
      cpu: "1"
      memory: "1Gi"

  database:
    tier: db-f1-micro
    version: POSTGRES_16
    storage_gb: 10
    high_availability: false

  cache:
    tier: basic
    memory_gb: 1
```

Best for: development, testing, demos, low-traffic production.

### Pro (~$80/mo)

```yaml
spec:
  compute:
    runtime:
      min_instances: 1
      max_instances: 5
      cpu: "2"
      memory: "2Gi"

  database:
    tier: db-g1-small
    version: POSTGRES_16
    storage_gb: 20
    high_availability: true

  cache:
    tier: standard
    memory_gb: 4
```

Best for: production workloads with auto-scaling and high availability.

---

## Environment-Specific Tips

### Development

```yaml
metadata:
  environment: dev

spec:
  compute:
    runtime:
      min_instances: 0       # Scale to zero when idle
      max_instances: 1

  database:
    tier: db-f1-micro
    high_availability: false

  cache:
    tier: basic
    memory_gb: 1
```

Cost-optimized for intermittent use. All services scale to zero. Expect cold starts of 5-15 seconds.

### Staging

```yaml
metadata:
  environment: staging

spec:
  provider:
    project: my-project-staging    # Separate GCP project recommended

  compute:
    runtime:
      min_instances: 1
      max_instances: 3
```

Mirror production settings at reduced scale. Use a separate GCP project to isolate staging resources.

### Production

```yaml
metadata:
  environment: production

spec:
  compute:
    runtime:
      min_instances: 1             # Never scale to zero
      max_instances: 10

  database:
    tier: db-g1-small
    high_availability: true        # Standby replica in different zone

  cache:
    tier: standard                 # Replication + automatic failover
    memory_gb: 4
```

Always keep at least one instance running for the runtime to eliminate cold starts. Enable HA on database and cache.

---

## Custom Images

Override default images to use private registries, specific versions, or custom builds:

```yaml
spec:
  images:
    runtime: us-docker.pkg.dev/my-project/astromesh/runtime:v0.7.0
```

When using Artifact Registry, ensure the Orbit service account has `roles/artifactregistry.reader` on the repository. Orbit does not grant this automatically — add it manually:

```bash
gcloud artifacts repositories add-iam-policy-binding astromesh \
  --project=my-project \
  --location=us-central1 \
  --member="serviceAccount:astromesh-orbit@my-project.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
```

---

## Validation Rules

Orbit validates the full configuration before any Terraform operation. Key rules:

| Rule | Error message |
|---|---|
| `max_instances` >= `min_instances` | `max_instances (1) must be >= min_instances (2) for compute.runtime` |
| `min_instances` >= 1 in production (runtime) | `production environment requires min_instances >= 1 for runtime` |
| `storage_gb` >= 10 | `database.storage_gb must be >= 10 (Cloud SQL minimum)` |
| `memory_gb` >= 1 for cache | `cache.memory_gb must be >= 1` |
| `provider.project` is non-empty | `spec.provider.project is required` |
| `provider.region` is a valid region | `'invalid-region' is not a valid GCP region` |
| `metadata.name` matches pattern | `metadata.name must match ^[a-z][a-z0-9-]{1,30}[a-z0-9]$` |

---

## Future Configuration (Roadmap)

`spec.storage` (v0.3.0) and `spec.observability` (v0.4.0) are implemented today — see the
[`spec.storage`](#specstorage) and [`spec.observability`](#specobservability) sections above. The
following sections are still planned and not yet implemented. They are shown commented out in
generated `orbit.yaml` files for reference:

```yaml
  # ── v0.5.0 — GPU & Inference ──
  # gpu:
  #   vllm:
  #     machine_type: g2-standard-4

  # ── v0.6.0 — Enterprise ──
  # domain:
  #   custom: agents.example.com
  #   ssl: managed
```

---

## Complete Example

A full `orbit.yaml` with all fields explicitly set:

```yaml
apiVersion: astromesh/v1
kind: OrbitDeployment
metadata:
  name: my-astromesh
  environment: production

spec:
  provider:
    name: gcp
    project: my-gcp-project-id
    region: us-central1

  compute:
    runtime:
      min_instances: 1
      max_instances: 5
      cpu: "2"
      memory: "2Gi"

  database:
    tier: db-g1-small
    version: POSTGRES_16
    storage_gb: 20
    high_availability: true

  cache:
    tier: standard
    memory_gb: 4

  secrets:
    provider_keys: true
    jwt_secret: true

  images:
    runtime: fulfarodev/astromesh:latest
```

---

## Related Docs

- **Overview:** [`ORBIT_OVERVIEW.md`](ORBIT_OVERVIEW.md)
- **Quick Start:** [`ORBIT_QUICKSTART.md`](ORBIT_QUICKSTART.md)
- **Design Spec:** [`superpowers/specs/2026-03-18-astromesh-orbit-design.md`](superpowers/specs/2026-03-18-astromesh-orbit-design.md)
