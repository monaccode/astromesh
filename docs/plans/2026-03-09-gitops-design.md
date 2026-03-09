# Astromesh Helm Chart Phase 4: GitOps with ArgoCD Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/helm-chart

---

## Overview

Add ArgoCD ApplicationSet for automated multi-environment deployment of Astromesh via GitOps.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Location | `deploy/gitops/argocd/` | Separate from chart, room for Flux later |
| Resource type | ApplicationSet with list generator | Balance of automation and clarity |
| Bootstrap | Direct kubectl apply | MVP, no App of Apps needed yet |

## Structure

```
deploy/gitops/argocd/
└── applicationset.yaml
```

## Environments

| Environment | Namespace | Values File | Auto-sync |
|-------------|-----------|-------------|-----------|
| dev | astromesh-dev | values-dev.yaml | Yes |
| staging | astromesh-staging | values-staging.yaml | Yes |
| prod | astromesh-prod | values-prod.yaml | Yes |

## Usage

```bash
kubectl apply -f deploy/gitops/argocd/applicationset.yaml
```
