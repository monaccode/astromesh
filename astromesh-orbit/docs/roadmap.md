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
