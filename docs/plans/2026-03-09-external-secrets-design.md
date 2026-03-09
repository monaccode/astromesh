# Astromesh Helm Chart Phase 5: External Secrets Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/helm-chart

---

## Overview

Add optional External Secrets Operator (ESO) resources to the Helm chart. Provider-agnostic templates for SecretStore and ExternalSecret. Assumes ESO is already installed in the cluster.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ESO installation | Not included (assumes pre-installed) | ESO is cluster-level, not per-app |
| Provider support | Generic (provider spec from values) | 20+ ESO providers, templates would go stale |
| Templates | SecretStore + ExternalSecret | Minimal surface, covers all use cases |

## New Templates

| Template | Condition | Purpose |
|----------|-----------|---------|
| `external-secret.yaml` | `externalSecrets.enabled` | Syncs secrets from external provider |
| `secret-store.yaml` | `externalSecrets.secretStore.enabled` | Configures the secret provider |

## Interaction with Existing Secrets

When `externalSecrets.enabled=true`, the ExternalSecret creates a K8s Secret with the same name as `astromesh.fullname`. This replaces the inline `secret.yaml`, so `secrets.create` should be `false`.
