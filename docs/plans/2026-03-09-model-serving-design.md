# Astromesh Helm Chart Phase 2: Extended Model Serving Design

**Date:** 2026-03-09
**Status:** Approved
**Branch:** feature/helm-chart

---

## Overview

Add vLLM and HuggingFace TEI (Text Embeddings Inference) as optional model serving components to the Astromesh Helm chart. Templates live directly in the chart (not subcharts). GPU scheduling is per-service.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| vLLM packaging | Templates in chart | Simple deployment, no stable external chart |
| TEI packaging | Single parametrized template | Avoids duplication, scales to N instances |
| GPU scheduling | Per-service nodeSelector/tolerations/resources | Each GPU service has different needs |

## New Templates

| Template | Conditional | Purpose |
|----------|-------------|---------|
| `deployment-vllm.yaml` | `vllm.enabled` | vLLM OpenAI-compatible server |
| `service-vllm.yaml` | `vllm.enabled` | Service for vLLM |
| `deployment-tei.yaml` | `tei.instances[]` | HF TEI per instance (embeddings, reranker) |
| `service-tei.yaml` | `tei.instances[]` | Service per TEI instance |

## New values.yaml Sections

```yaml
vllm:
  enabled: false
  image:
    repository: vllm/vllm-openai
    tag: latest
    pullPolicy: IfNotPresent
  model: "mistralai/Mistral-7B-Instruct-v0.3"
  extraArgs:
    - "--max-model-len"
    - "4096"
  service:
    type: ClusterIP
    port: 8000
  resources:
    limits:
      nvidia.com/gpu: "1"
  nodeSelector: {}
  tolerations: []

tei:
  instances: []
  image:
    repository: ghcr.io/huggingface/text-embeddings-inference
    tag: latest
    pullPolicy: IfNotPresent
  service:
    type: ClusterIP
```

## TEI Instance Schema

Each TEI instance in `tei.instances[]`:

```yaml
- name: embeddings          # Used in resource naming
  modelId: "BAAI/bge-small-en-v1.5"
  port: 8002                # Container and service port
  resources: {}             # Optional GPU resources
  nodeSelector: {}          # Optional node selection
  tolerations: []           # Optional tolerations
```

## Environment Values Updates

- `values-dev.yaml`: Enable vLLM + TEI embeddings (no GPU limits)
- `values-prod.yaml`: Add GPU resources and nodeSelector examples
