# Astromesh Orbit Roadmap

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
> The 0.2.0 version number was published without this content. Delivered in v0.4.0 below.

### v0.3.0 — Storage & RAG  ✅
- Cloud Storage bucket for RAG documents (wired to the runtime via `ASTROMESH_RAG_BUCKET`)
- Artifact Registry for custom images
- pgvector on the existing Cloud SQL as the RAG vector store (no separate vector DB)
- ~~Cloud CDN for Studio~~ — dropped; Studio is no longer deployed (see commit 6278ccc)

### v0.4.0 — Observability  ✅
- Cloud Monitoring dashboard (Cloud Run golden signals; on by default)
- Cloud Trace via an OpenTelemetry Collector sidecar (opt-in: `observability.tracing.enabled`)
- `orbit logs` (reads Cloud Run logs from Cloud Logging)
- `orbit upgrade` (re-renders templates and shows a diff)
- No `logging` toggle: Cloud Run ships logs to Cloud Logging for free

### v0.5.0 — GPU & Inference
- Cloud Run with GPU (vLLM)
- Embeddings service (TEI on Cloud Run)
- Reranker service

### v0.6.0 — Enterprise
- Cloud Armor (WAF)
- Custom domains + managed SSL
- Native VPC (no connector)
- Cloud DNS

### v1.0.0 — Multi-Cloud
- AWS provider (ECS/Fargate + RDS + ElastiCache)
- Azure provider (Container Apps + Azure DB + Azure Cache)
- GCP, AWS and Azure Marketplace listings
