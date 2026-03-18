# Astromesh Orbit — Cloud-Native Deployment Design Spec

**Date:** 2026-03-18
**Status:** Approved
**Author:** Juan Carlos Romero + Claude

## Overview

Astromesh Orbit is a standalone subproject (`astromesh-orbit/`) that provides cloud-native, one-command deployment of the full Astromesh stack to any major cloud provider. It generates Terraform HCL from Jinja2 templates, with a provider plugin architecture that makes adding new clouds a matter of implementing a provider and its templates.

The vision is marketplace-ready deployments: GCP first, then AWS and Azure. The user experience ranges from a zero-config wizard to a fully declarative `orbit.yaml`, with an escape hatch (`eject`) that produces standalone Terraform files.

## Goals

1. **One-command deploy** — `astromeshctl orbit apply` provisions a production-ready Astromesh stack on GCP using managed cloud services (Cloud Run, Cloud SQL, Memorystore).
2. **Cloud-native by default** — Use each cloud's managed services instead of self-hosted equivalents. PostgreSQL → Cloud SQL, Redis → Memorystore, compute → Cloud Run.
3. **Multi-cloud foundation** — Provider plugin architecture allows adding AWS and Azure without changing the core or CLI.
4. **Marketplace path** — Architecture supports GCP Marketplace listing (Cloud Run integration) with GKE Marketplace as a future enterprise option.
5. **Escape hatch** — `orbit eject` produces clean, standalone Terraform files with no Orbit dependency.

## Non-Goals (MVP)

- GKE Marketplace listing (v2 — existing Helm chart covers Kubernetes users)
- AWS or Azure providers (v1.0 roadmap)
- GPU/inference provisioning (v0.4 roadmap)
- Observability stack provisioning (v0.2 roadmap)
- Custom domain / SSL management (v0.5 roadmap)

## Architecture

### Subproject Structure

```
astromesh-orbit/
├── pyproject.toml              # astromesh-orbit[gcp,aws,azure]
├── astromesh_orbit/
│   ├── __init__.py
│   ├── cli.py                  # Entry point: registers as astromeshctl plugin
│   ├── config.py               # OrbitConfig — parses orbit.yaml
│   ├── core/
│   │   ├── provider.py         # OrbitProvider Protocol
│   │   ├── state.py            # State tracker (reads terraform.tfstate from bucket)
│   │   └── resources.py        # Typed dataclasses: ComputeSpec, DatabaseSpec, CacheSpec
│   ├── terraform/
│   │   ├── runner.py           # Wrapper: init, plan, apply, destroy, output
│   │   └── backend.py          # Configures remote state (GCS, S3, Azure Blob)
│   ├── wizard/
│   │   ├── interactive.py      # Interactive wizard (typer/rich prompts)
│   │   └── defaults.py         # Defaults per tier (starter, pro)
│   └── providers/
│       └── gcp/
│           ├── __init__.py
│           ├── provider.py     # GCPProvider(OrbitProvider)
│           ├── validators.py   # Validates project, permissions, enabled APIs
│           └── templates/      # .tf.j2 Jinja2 templates
│               ├── main.tf.j2
│               ├── cloud_run.tf.j2
│               ├── cloud_sql.tf.j2
│               ├── memorystore.tf.j2
│               ├── secrets.tf.j2
│               ├── networking.tf.j2
│               ├── iam.tf.j2
│               ├── variables.tf.j2
│               ├── outputs.tf.j2
│               └── backend.tf.j2
├── tests/
│   ├── test_config.py
│   ├── test_wizard.py
│   ├── test_terraform_runner.py
│   └── providers/
│       └── test_gcp_provider.py
└── docs/
    └── roadmap.md
```

### Provider Plugin Architecture

Each cloud provider implements the `OrbitProvider` Protocol (following the existing `@runtime_checkable` convention from `astromesh/providers/base.py`):

```python
from dataclasses import dataclass

@dataclass
class CheckResult:
    name: str               # e.g. "gcp_project_exists", "apis_enabled"
    passed: bool
    message: str            # human-readable description
    remediation: str | None # e.g. "gcloud services enable sqladmin.googleapis.com"

@dataclass
class ValidationResult:
    ok: bool
    checks: list[CheckResult]

@dataclass
class PlanResult:
    resources_to_create: list[str]
    resources_to_update: list[str]
    resources_to_destroy: list[str]
    raw_output: str         # full terraform plan text
    estimated_monthly_cost: float | None  # derived from wizard presets if available

@dataclass
class ApplyResult:
    success: bool
    outputs: dict[str, str] # terraform outputs (URLs, IPs, connection strings)
    raw_output: str

@dataclass
class ProvisionResult:
    apply: ApplyResult
    env_file: Path          # path to generated orbit.env
    endpoints: dict[str, str]  # {"runtime": "https://...", "cloud_api": "https://...", "studio": "https://..."}

@dataclass
class ResourceStatus:
    name: str               # e.g. "astromesh-runtime"
    resource_type: str      # e.g. "cloud_run_v2_service"
    status: str             # "running", "stopped", "error", "not_found"
    url: str | None

@dataclass
class DeploymentStatus:
    resources: list[ResourceStatus]
    state_bucket: str
    last_applied: str | None  # ISO timestamp from state

@runtime_checkable
class OrbitProvider(Protocol):
    name: str  # "gcp", "aws", "azure"

    async def validate(self, config: OrbitConfig) -> ValidationResult:
        """Validate credentials, permissions, enabled APIs, quotas."""

    async def generate(self, config: OrbitConfig, output_dir: Path) -> list[Path]:
        """Generate .tf files from Jinja2 templates. Return generated paths."""

    async def provision(self, config: OrbitConfig, output_dir: Path) -> ProvisionResult:
        """validate() + generate() + terraform apply. Return endpoints and credentials."""

    async def status(self, config: OrbitConfig) -> DeploymentStatus:
        """Read terraform state and return current status of each resource."""

    async def destroy(self, config: OrbitConfig, output_dir: Path) -> None:
        """terraform destroy + clean up state bucket."""

    async def eject(self, config: OrbitConfig, output_dir: Path) -> Path:
        """Generate clean .tf files (no Jinja2) for standalone Terraform management."""
```

### Execution Flow

```
orbit.yaml → OrbitProvider.validate() → OrbitProvider.generate()
           → TerraformRunner.init() → TerraformRunner.plan()
           → TerraformRunner.apply() → post-provisioning (orbit.env)
```

1. `astromeshctl orbit init` — wizard generates `orbit.yaml`
2. `astromeshctl orbit plan` — validate → generate `.tf` → `terraform plan` (preview)
3. `astromeshctl orbit apply` — provision → `terraform apply` → show endpoints
4. `astromeshctl orbit status` — read state → show resource status
5. `astromeshctl orbit destroy` — `terraform destroy`
6. `astromeshctl orbit eject` — generate standalone `.tf` files in `./orbit-terraform/`

### Terraform Runner

Thin wrapper around the `terraform` CLI binary (executed as subprocess):

```python
class TerraformRunner:
    async def init(self, work_dir: Path) -> None
    async def plan(self, work_dir: Path) -> PlanResult
    async def apply(self, work_dir: Path, auto_approve: bool = False) -> ApplyResult
    async def destroy(self, work_dir: Path, auto_approve: bool = False) -> None
    async def output(self, work_dir: Path) -> dict[str, str]
```

Terraform is a required external binary, not a Python dependency. `orbit init` validates its presence and offers installation guidance if missing.

### State Management

Terraform state is stored remotely in a cloud bucket owned by the user:

- **GCP:** GCS bucket `{project}-astromesh-orbit-state` in the same region. GCS natively supports Terraform state locking — concurrent `orbit apply` calls are safely serialized.
- **AWS (future):** S3 bucket with DynamoDB locking
- **Azure (future):** Azure Blob with lease locking

The state bucket is the only resource created via cloud SDK directly (before Terraform can initialize). Details:

- **Creation:** If the bucket does not exist, Orbit creates it with versioning enabled (recommended for Terraform state recovery).
- **Reuse:** If the bucket already exists (e.g., from a previous deployment), it is reused as-is.
- **Naming collision:** If the bucket name is taken by another GCP project, Orbit appends a 6-char hash suffix and retries.
- **Permissions:** Requires `storage.buckets.create` on the project. If the user lacks this permission but the bucket already exists, Orbit proceeds normally. If both fail, clear error with remediation: `"Grant roles/storage.admin or create the bucket manually: gsutil mb gs://{bucket_name}"`.
- **Cleanup:** `orbit destroy` does NOT delete the state bucket (it contains the state needed to know what was destroyed). The user can delete it manually after confirming everything is torn down.

### Working Directory

```
.orbit/
  generated/          # .tf files (gitignored)
  orbit.env           # Connection variables post-deploy
  .terraform/         # Terraform cache (gitignored)
```

Only `orbit.yaml` is committed to git. `.orbit/` is gitignored. The `orbit init` command appends `.orbit/` to the project's `.gitignore` if not already present.

## Configuration

### orbit.yaml Schema

```yaml
apiVersion: astromesh/v1
kind: OrbitDeployment
metadata:
  name: my-astromesh
  environment: production       # dev | staging | production

spec:
  provider:
    name: gcp
    project: my-gcp-project-id
    region: us-central1

  compute:
    runtime:                    # Astromesh core runtime
      min_instances: 1
      max_instances: 5
      cpu: "2"
      memory: "2Gi"
    cloud_api:                  # Astromesh Cloud API
      min_instances: 1
      max_instances: 3
      cpu: "1"
      memory: "1Gi"
    studio:                     # Astromesh Cloud Studio (Next.js)
      min_instances: 0          # scale to zero
      max_instances: 2

  database:
    tier: db-f1-micro           # GCP Cloud SQL tier
    version: POSTGRES_16
    storage_gb: 10
    high_availability: false

  cache:
    tier: basic                 # basic | standard
    memory_gb: 1

  secrets:
    provider_keys: true         # Creates empty Secret Manager entries; user populates via GCP Console or gcloud
    jwt_secret: true            # Auto-generated random value on first deploy

  # ── Future services (roadmap, not implemented in v1) ──
  # monitoring:
  #   enabled: false
  # storage:
  #   rag_bucket: true
  # gpu:
  #   vllm:
  #     machine_type: g2-standard-4
  # artifact_registry:
  #   enabled: false

  images:
    runtime: fulfarodev/astromesh:latest
    cloud_api: fulfarodev/astromesh-cloud-api:latest
    studio: fulfarodev/astromesh-cloud-studio:latest
```

### Wizard Presets

- **Starter (~$30/mo):** 1 instance each, db-f1-micro, 1GB cache, no HA
- **Pro (~$150/mo):** auto-scaling (1-5), db-g1-small with HA, 4GB cache

The wizard writes explicit values to `orbit.yaml` — no magic tier references at runtime.

## GCP Provider Details

### Resource Mapping

| orbit.yaml | GCP Resource | Template |
|---|---|---|
| `spec.compute.runtime` | Cloud Run Service | `cloud_run.tf.j2` |
| `spec.compute.cloud_api` | Cloud Run Service | `cloud_run.tf.j2` |
| `spec.compute.studio` | Cloud Run Service | `cloud_run.tf.j2` |
| `spec.database` | Cloud SQL for PostgreSQL | `cloud_sql.tf.j2` |
| `spec.cache` | Memorystore for Redis | `memorystore.tf.j2` |
| `spec.secrets` | Secret Manager | `secrets.tf.j2` |
| (automatic) | Serverless VPC Connector | `networking.tf.j2` |
| (automatic) | Service Account + IAM | `iam.tf.j2` |
| (automatic) | GCS Bucket (terraform state) | `backend.tf.j2` |

### Automatic Resources

Resources provisioned automatically (not user-configured):

- **VPC Connector** — Cloud Run requires Serverless VPC Access to reach Cloud SQL and Memorystore in private VPC.
- **Service Account** — Dedicated SA `astromesh-orbit@{project}` with minimum roles: `roles/cloudsql.client`, `roles/redis.editor`, `roles/secretmanager.secretAccessor`, `roles/run.invoker`.
- **IAM bindings** — Cloud Run services run as the dedicated SA.
- **Cloud SQL Auth Proxy** — Cloud Run connects to Cloud SQL via the built-in proxy sidecar (`--add-cloudsql-instances` flag), not public IP.

### Pre-deploy Validation

`GCPProvider.validate()` checks:

1. `gcloud` CLI is authenticated
2. GCP project exists and user has `roles/owner` or `roles/editor`
3. Required APIs are enabled: `run.googleapis.com`, `sqladmin.googleapis.com`, `redis.googleapis.com`, `secretmanager.googleapis.com`, `vpcaccess.googleapis.com`
4. If any API is not enabled, offers to enable it automatically
5. Quota checks (Cloud SQL instances, Cloud Run services)

### Post-Provisioning

After `terraform apply`, Orbit reads Terraform outputs and generates `orbit.env`:

```env
ASTROMESH_DATABASE_URL=postgresql+asyncpg://astromesh:***@/astromesh?host=/cloudsql/{connection_name}
ASTROMESH_REDIS_URL=redis://{memorystore_ip}:6379
ASTROMESH_CLOUD_DATABASE_URL=postgresql+asyncpg://cloudapi:***@/astromesh_cloud?host=/cloudsql/{connection_name}
ASTROMESH_CLOUD_RUNTIME_URL=https://{runtime_cloud_run_url}
ASTROMESH_CLOUD_JWT_SECRET=projects/{project}/secrets/jwt-secret/versions/latest
```

## CLI Interface

### Plugin Discovery

`astromesh-orbit` registers via Python entry points:

```toml
[project.entry-points."astromeshctl.plugins"]
orbit = "astromesh_orbit.cli:register"
```

**Prerequisite:** The core `cli/main.py` currently has no plugin discovery logic — all commands are statically imported. As part of Orbit implementation, a plugin discovery mechanism must be added to the core CLI:

1. On startup, `cli/main.py` scans `importlib.metadata.entry_points(group="astromeshctl.plugins")`
2. Each entry point exposes a `register(app: typer.Typer)` function that adds its subcommand group
3. If scanning finds no entry point for a given subcommand (e.g., `orbit`), the CLI shows:
   ```
   Command 'orbit' not found. Install it with:
     pip install astromesh-orbit[gcp]
   ```

This change to the core CLI is a blocking dependency for Orbit and also benefits future CLI extensions.

### Commands

```
astromeshctl orbit init [--provider gcp] [--preset starter|pro]
astromeshctl orbit plan [--config orbit.yaml]
astromeshctl orbit apply [--config orbit.yaml] [--auto-approve]
astromeshctl orbit status [--config orbit.yaml]
astromeshctl orbit destroy [--config orbit.yaml] [--auto-approve]
astromeshctl orbit eject [--output-dir ./terraform]
```

Note: `orbit logs` is deferred to v0.2.0 (Observability) when Cloud Logging integration is implemented.

## Dependencies

```toml
[project]
name = "astromesh-orbit"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "jinja2>=3.1",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "rich>=13.0",
    "typer>=0.12",
]

[project.optional-dependencies]
gcp = ["google-cloud-resource-manager>=1.12", "google-auth>=2.29"]
aws = []   # future
azure = [] # future
all = ["astromesh-orbit[gcp]"]

[project.entry-points."astromeshctl.plugins"]
orbit = "astromesh_orbit.cli:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "orbit_gcp: tests that create real GCP resources (deselect with -m 'not orbit_gcp')",
]
```

Key decisions:
- **No dependency on `astromesh` core** — Orbit is pure provisioning. Independent package.
- **Terraform is external** — Not a Python dependency. Required binary validated at runtime.
- **GCP SDK is minimal** — Only `google-cloud-resource-manager` and `google-auth` for pre-deploy validation. Terraform does the actual provisioning.
- **Same tooling as core** — hatchling, ruff, pytest. Consistent with the monorepo.

## Testing Strategy

- **Unit tests** — `OrbitConfig` parsing, Jinja2 template rendering, wizard defaults. No cloud credentials needed.
- **Template snapshot tests** — Given an `orbit.yaml` fixture, verify generated `.tf` files match a snapshot. Catches accidental template changes.
- **Integration tests** — Marked with `@pytest.mark.orbit_gcp`. Create real GCP resources in a test project, validate the stack works, destroy everything. Run in CI with a dedicated service account, not on every PR.

## Service Roadmap

### v0.1.0 — Core (MVP)
- Cloud Run (runtime, cloud-api, studio)
- Cloud SQL for PostgreSQL
- Memorystore for Redis
- Secret Manager
- VPC Connector + IAM
- Terraform state in GCS
- CLI: init, plan, apply, status, destroy, eject
- Interactive wizard with presets

### v0.2.0 — Observability
- Cloud Monitoring (Cloud Run metrics)
- Cloud Trace (replaces OTEL Collector)
- Cloud Logging (structured logs)
- Pre-configured dashboard
- `orbit logs` CLI command (Cloud Logging integration)
- `orbit upgrade` command (regenerates templates after package update, shows diff)

### v0.3.0 — Storage & RAG
- Cloud Storage bucket for RAG documents
- Artifact Registry for custom images
- Cloud CDN for Studio

### v0.4.0 — GPU & Inference
- Cloud Run with GPU (vLLM)
- Embeddings service (TEI on Cloud Run)
- Reranker service

### v0.5.0 — Enterprise
- Cloud Armor (WAF)
- Custom domains + managed SSL
- Native VPC (no connector)
- Cloud DNS

### v1.0.0 — Multi-Cloud
- AWS provider (ECS/Fargate + RDS + ElastiCache)
- Azure provider (Container Apps + Azure DB + Azure Cache)
- GCP Marketplace listing
- AWS Marketplace listing
- Azure Marketplace listing

## Error Handling

- **`terraform apply` failure mid-way:** Terraform handles partial rollback via state. Orbit shows which resources were created and which failed. User can re-run `orbit apply` (idempotent) or `orbit destroy` to clean up.
- **Validation failures:** `validate()` runs before any Terraform operation. Clear error messages with remediation steps (e.g., "Enable sqladmin.googleapis.com with: gcloud services enable sqladmin.googleapis.com").
- **Missing Terraform:** Detected at `orbit init`. Shows installation instructions.
- **Missing cloud credentials:** Detected at `validate()`. Shows `gcloud auth login` instructions.

## Eject Details

`orbit eject` produces a self-contained Terraform directory:

- **`backend.tf`** — Points to the existing state bucket so the user takes over the same state. No migration needed.
- **`terraform.tfvars`** — All values from `orbit.yaml` resolved into Terraform variables. No inlined values in `.tf` files.
- **Reversibility** — After ejecting, `orbit apply` still works (it regenerates `.orbit/generated/` from `orbit.yaml`). Eject is non-destructive; it only writes to the output directory. However, if the user modifies the ejected files and applies them directly with `terraform apply`, the state diverges from what Orbit expects — subsequent `orbit apply` calls will detect drift and warn.
- **Comments** — Ejected files include explanatory comments (e.g., `# Cloud SQL instance for Astromesh runtime database`) that the Jinja2 templates do not.
