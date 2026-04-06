# Changelog

All notable changes to astromesh-orbit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
