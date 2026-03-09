# Astromesh Helm Chart Phase 6: Kubernetes Operator CRDs Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/helm-chart

---

## Overview

Define CRDs for the future Astromesh Kubernetes Operator. CRD definitions only (no controller). Schemas are essential with additionalProperties for flexibility. Placed in Helm `crds/` directory for automatic installation and deletion protection.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | CRD definitions + docs only | Controller is a separate project |
| Schema depth | Essential + additionalProperties | Avoids rigid sync with Python code |
| Location | `deploy/helm/astromesh/crds/` | Helm convention, deletion protection |

## CRDs

| CRD | Group | Kind | Scope |
|-----|-------|------|-------|
| `agents.astromesh.io` | astromesh.io | Agent | Namespaced |
| `providers.astromesh.io` | astromesh.io | Provider | Namespaced |
| `channels.astromesh.io` | astromesh.io | Channel | Namespaced |
| `ragpipelines.astromesh.io` | astromesh.io | RAGPipeline | Namespaced |

All use API version `v1alpha1` with status subresource.

## Future Reconciliation Logic

| CRD | Reconciler Action |
|-----|-------------------|
| Agent | Create/update ConfigMap, restart pods on change |
| Provider | Update providers.yaml ConfigMap, run health check |
| Channel | Update channels.yaml ConfigMap |
| RAGPipeline | Configure RAG pipeline in runtime |
