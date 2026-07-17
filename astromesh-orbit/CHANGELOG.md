# Changelog

All notable changes to astromesh-orbit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-07-14

### Added

- **Observability config schema** (`spec.observability`): opt-in blocks for the Cloud Monitoring dashboard, structured logging, and Cloud Trace, with dashboard/logging on and tracing off by default (`astromesh_orbit/config.py`)
- **Cloud Monitoring dashboard** rendered from `monitoring.tf.j2` and wired into the GCP provider's observability context
- **OTel Collector sidecar**: `orbit apply` provisions a collector sidecar and injects the OTLP env for the runtime to export spans to **Cloud Trace** (paired with core's OTLP wiring shipped in astromesh v0.33.0)
- **`orbit logs`**: reads Cloud Logging for the workspace via `gcloud`
- **`orbit upgrade`**: template-diff command that shows and applies drift between the workspace's rendered templates and the current provider templates
- **Observability block in wizard presets**, so `orbit init` scaffolds the new config
- IAM: grants **Cloud Trace** and **metric-writer** roles when tracing is enabled; requires the `monitoring`, `cloudtrace` and `logging` APIs during validation

### Fixed

- **`orbit upgrade` prunes dropped templates** instead of leaving stale files behind when a template is removed from the provider

## [0.3.0] - 2026-07-14

### Added

- **Storage config schema** (`spec.storage`): declares the GCS RAG documents bucket and the Artifact Registry repo for custom images (`astromesh_orbit/config.py`)
- **GCS RAG documents bucket** rendered from `storage.tf.j2` and wired into the GCP provider render
- **Artifact Registry repo** rendered from `artifact_registry.tf.j2` for custom runtime images
- **`ASTROMESH_RAG_BUCKET` env** and storage outputs exposed to the runtime so RAG can resolve its bucket at boot
- **Storage block in wizard presets**, so `orbit init` scaffolds the new config
- Requires the `storage` and `artifactregistry` APIs during validation

## [0.2.0] - 2026-05-20

### Added

- **Custom env vars in Cloud Run**: `OrbitSpec.env` dict rendered as additional `env` blocks in the Cloud Run template — enables Cortex to inject workspace environment variables during provision (`astromesh_orbit/providers/gcp/templates/cloud_run.tf.j2`)
- **`OrbitMetadata.environment`** now accepts `develop | staging | production` (was only `dev`)
- **Dual-auth support**: provider validators and Terraform runner work with either a service-account JSON key OR an authenticated `gcloud` CLI — picks whichever is available
- **Auto VPC peering**: `orbit apply` now configures the VPC peering between the workspace and Cloud SQL automatically (was a manual post-apply step)
- **Lock-free ops + `init reconfigure`**: removes the local-state lock that blocked concurrent runs; `orbit init` learned a `--reconfigure` flag to refresh derived fields without re-running the full wizard
- **`TOFU_PATH` env var**: `TerraformRunner` reads `TOFU_PATH` with a fallback chain (`TOFU_PATH` → `tofu` on PATH → `terraform` on PATH) so OpenTofu users no longer need to symlink the binary

### Changed

- **Cloud Run services are public by default** (`allUsers` IAM binding on `roles/run.invoker`) — enables Cortex (browser) to call the runtime API without an IAM token. Existing private services are unaffected; explicit `allow_unauthenticated: false` still wins.
- **`google-cloud-storage` API for state bucket** instead of shelling out to `gsutil` — removes the gsutil dependency from the local install requirements and surfaces typed errors instead of shell exit codes (`astromesh_orbit/providers/gcp/state.py`)

### Fixed

- **Cloud Run container `PORT`**: removed the reserved `PORT` env var from the Cloud Run template — Cloud Run sets it automatically from the `ports` block, and setting it explicitly was rejected by the Run API
- **Cloud Run container port = 8000**: aligned the Cloud Run template port with the runtime image's default listen port (was 8080)
- **Missing `gcloud` CLI**: validators no longer crash with `FileNotFoundError`; they emit a structured validation error instead, so `orbit init` works on machines without gcloud installed
- **Windows cp1252 compatibility**: replaced Unicode arrows/symbols in console output with ASCII equivalents — prevents `UnicodeEncodeError` on Windows terminals using cp1252

## [0.1.2] - 2026-04-06

### Fixed

- **Windows support**: Use `gcloud.cmd` instead of `gcloud` in `asyncio.create_subprocess_exec` — fixes `FileNotFoundError` when running `astromeshctl orbit plan/apply` on Windows, where `.cmd` scripts are not resolved from PATH by `subprocess_exec`

## [0.1.1] - 2026-03-28

### Added

- GCP provider with Cloud Run, Cloud SQL, Redis, Secret Manager support
- `orbit init` interactive wizard for generating `orbit.yaml`
- `orbit plan` / `orbit apply` / `orbit destroy` / `orbit status` commands
- Terraform template generation for GCP infrastructure
- Validation checks (gcloud auth, project, APIs enabled)
- Plugin registration via `astromeshctl.plugins` entry point

## [0.1.0] - 2026-03-25

- Initial release
