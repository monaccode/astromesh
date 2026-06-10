# Astromesh Nebula · Centinela family · v0.1 (Centinela-4B) — Design Spec

- **Date:** 2026-06-09
- **Status:** Approved for planning
- **Author:** Juan Carlos Romero (with Claude Code)
- **Source idea:** `astromesh llm.md` (AstroMesh-Fin / Centinela spec)

---

## 1. Summary

**Astromesh Nebula** is a new sibling project: an open-model *foundry* where Astromesh
creates, trains, evaluates, quantizes, and publishes its open-source LLMs. It is named for a
**nebula — a stellar nursery where stars are born** — and joins the cosmic ecosystem (Orbit,
Nexus, Cortex, Forge, Node, OS, Leia).

- **Astromesh Nebula** — the umbrella project / model foundry (the repo). *Where models are born.*
- **Centinela** — the **first model family** born in the Nebula (Spanish-first financial &
  administrative models; the vertical formerly called "AstroMesh-Fin").
- **Centinela-4B** (`Qwen/Qwen3-4B`) — the **first concrete model** and the scope of this spec
  (v0.1 vertical slice).

This spec covers **only the v0.1 vertical slice**: train and publish one real model end-to-end to
prove the full MLOps chain. Centinela-8B, the router, vLLM serving, and k3s/ArgoCD are explicitly
deferred to later iterations.

## 2. Goals & non-goals

### Goals (v0.1)
- Ship a **real, public** model on the Hugging Face Hub: `HF_ORG/Centinela-Qwen3-4B`.
- Prove the **entire pipeline** end-to-end: eval-first → dataset → train (HF Jobs) → merge →
  quantize (GGUF) → evaluate → publish (model repo + model card + dataset card + Gradio Space).
- Establish repo conventions, OSS governance, and CI gates that future families/models reuse.
- Keep the economic thesis intact: small model + deterministic validation + no frontier dependency.

### Non-goals (deferred)
- **Centinela-8B** (reasoning tier) — replicate after the 4B slice works.
- **Router** (4B → 8B → frontier) — nothing to route to yet with a single model.
- **Serving:** vLLM OpenAI-compatible server, AWQ quantization.
- **Infra:** k3s / ArgoCD / Helm GitOps, full `docker-compose` stack.
- **Frontier baseline** in eval (Anthropic API) — too costly; behind an off-by-default flag.

## 3. Key design decisions (and why)

| Decision | Choice | Rationale |
|---|---|---|
| Objective | Real shippable model, public data | No private/PII dataset needed to start. |
| Compute | **HF Jobs (cloud GPU)** | No local GPU (Windows host); same ecosystem as publishing; reproducible; `huggingface-llm-trainer` skill orchestrates TRL/Unsloth. |
| Route/scope | **Vertical 4B → HF**, defer the rest | Proves the full thesis at minimum cost/risk before scaling. |
| First task | **Spanish financial text classification** (sentiment/topic) | The only Tier-1 task with *real public Spanish* data — preserves the "Spanish-first" claim with zero translation. |
| Dataset | `NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1`, filtered to ES | Bilingual EN+ES, 10k–100k rows, Apache-2.0; we use the Spanish rows. |
| Frontier baseline | Off by default (`--frontier` flag) | Anthropic comparison is expensive; base-vs-finetune is free and sufficient. |
| Project name | **Astromesh Nebula** | Stellar nursery = "where models are born"; fits cosmic ecosystem; no model-line collision. |
| Repo location | New sibling repo `astromesh-nebula` | MLOps concern is independent from the FastAPI runtime; its own `pyproject`, no version-sync entanglement. |

### 3.1 The Spanish-data finding (important)

A Hugging Face search confirmed that **Spanish-native finance datasets are scarce**. The
high-quality finance instruction/classification data is in **English** (`gbharti/finance-alpaca`,
`takala/financial_phrasebank`, `FinGPT/*`). The original spec's flagship task — *invoice field
extraction in Spanish* — has **no good public Spanish dataset**. Therefore v0.1 pivots to **Spanish
financial classification** using the bilingual NickyNicky dataset, the highest-integrity option for
a genuinely Spanish-first first model. Extraction and QA tasks return in later iterations (likely
via EN→ES translation or synthetic generation, evaluated separately).

## 4. Architecture / repo layout

A foundry that can host **multiple families** over time. Centinela is family #1. v0.1 keeps the
tree simple but names things so future families get their own `data/` + `configs/` namespace.

```
astromesh-nebula/
├── README.md                  # foundry overview + Centinela family
├── LICENSE                    # Apache-2.0
├── NOTICE                     # Qwen base-model license attribution
├── CLAUDE.md                  # short build notes for Claude Code
├── CONTRIBUTING.md            # OSS contribution guide
├── CODE_OF_CONDUCT.md
├── SECURITY.md                # responsible disclosure
├── CITATION.cff               # how to cite the models
├── Makefile                   # train/eval/quantize/publish (SIZE=4b)
├── pyproject.toml             # deps, pinned (uv)
├── .gitignore                 # /data/raw, /checkpoints, *.gguf, .env
├── .env.example               # HF_TOKEN, WANDB_API_KEY (no secrets committed)
│
├── .github/
│   ├── workflows/
│   │   ├── eval-gate.yml       # CI: run eval, block regressions below tier threshold
│   │   └── publish.yml         # on tag v*: quantize + push artifacts to HF Hub
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── data/                       # namespaced per family
│   └── centinela/
│       ├── raw/                # gitignored (here: cached HF dataset)
│       ├── processed/
│       ├── train.jsonl
│       ├── eval.jsonl          # built BEFORE training
│       └── README.md           # dataset card: source (NickyNicky), sizes, labels, license
│
├── configs/
│   ├── train-4b.yaml           # QLoRA hyperparams for Centinela-4B
│   └── eval.yaml               # tasks, labels, tier threshold (e.g. macro-F1 ≥ 0.85)
│
├── scripts/
│   ├── 01_build_dataset.py     # NickyNicky → filter ES → chat JSONL + train/eval split
│   ├── 02_train.py             # QLoRA on Qwen3-4B (Unsloth/TRL) — runs as HF Job; --size 4b
│   ├── 03_merge.py             # merge LoRA → bf16 safetensors
│   ├── 04_quantize.sh          # GGUF Q4_K_M (Ollama). AWQ deferred.
│   ├── 05_evaluate.py          # base Qwen3-4B vs Centinela-4B (--frontier optional)
│   ├── 06_push_to_hub.py       # repo + adapter + merged + GGUF + model card + tag v0.1
│   ├── 07_publish_dataset.py   # publish processed ES split + card (public data, no PII)
│   └── 08_deploy_space.py      # build/deploy Gradio demo Space (loads GGUF, CPU)
│
├── eval/
│   ├── tasks/                  # classification task with gold labels (ES held-out)
│   └── results/results.md      # committed comparison report (feeds the model card)
│
├── nebula/                     # small shared library
│   └── validation.py           # deterministic output-constraining (label ∈ allowed set)
│
├── demo/                       # public Hugging Face Space (Gradio)
│   ├── app.py
│   ├── requirements.txt
│   └── README.md               # Space card (YAML header: sdk: gradio)
│
└── model_card/
    └── Centinela-4B.md         # rendered template, eval table injected, pushed as repo README
```

Deferred-and-omitted vs the original spec: `serving/`, `deploy/`, `router/`, `configs/train-8b.yaml`,
`values-8b.yaml`, AWQ artifacts.

## 5. The task & eval contract

- **Task:** Spanish financial text classification. Input = a Spanish financial sentence/snippet.
  Output = a single label from a **closed set** (sentiment and/or topic, finalized from the
  dataset's label inventory in `01_build_dataset.py`).
- **Eval-first:** the held-out **Spanish** eval split and gold labels are defined in `eval/tasks/`
  **before** any training. `configs/eval.yaml` sets the metric (**macro-F1 + accuracy**) and the
  **tier threshold** (initial target: macro-F1 ≥ 0.85 *and* strictly better than base Qwen3-4B
  few-shot). A model below threshold **does not ship** — enforced in CI.
- **Baselines:** base `Qwen/Qwen3-4B` (few-shot prompt) vs `Centinela-4B`. Optional `--frontier`
  (Claude) is off by default.
- **Deterministic validation layer (`nebula/validation.py`):** the model's output is constrained to
  the allowed label set; out-of-set outputs are rejected/retried and counted. This is the
  classification-flavored version of the spec's non-negotiable "LLM never guesses freely" principle.

## 6. Pipeline & data flow

1. **Eval harness first** — define gold ES eval + thresholds (`eval/tasks/`, `configs/eval.yaml`).
2. **Build dataset** — `01_build_dataset.py`: pull NickyNicky from HF, filter to Spanish rows, map
   to chat JSONL (`system`: Spanish classifier instruction; `user`: text; `assistant`: label),
   split train/eval, write dataset card. (~1k–5k specialize; ensure no eval leakage into train.)
3. **Train** — `02_train.py --size 4b` as an **HF Job**: QLoRA on Qwen3-4B (Unsloth/TRL),
   `r=16, lora_alpha=16, lr=2e-4, epochs=1–3`, target = attention + MLP projections, gradient
   checkpointing on. Monitored via Trackio.
4. **Merge** — `03_merge.py`: LoRA → bf16 safetensors.
5. **Quantize** — `04_quantize.sh`: GGUF Q4_K_M (Ollama-ready).
6. **Evaluate** — `05_evaluate.py`: base vs Centinela-4B on the held-out ES eval → `eval/results/results.md`.
7. **Gate** — if below tier threshold, stop (CI fails / `make publish` aborts).
8. **Publish** — `06_push_to_hub.py`: create public repo, upload adapter + merged + GGUF, render
   model card (eval table injected) as README, tag `v0.1`.
9. **Publish dataset** — `07_publish_dataset.py`: processed ES split + dataset card with NickyNicky
   attribution (public source, no PII).
10. **Demo** — `08_deploy_space.py`: Gradio Space loading the GGUF (CPU) with safe Spanish examples.

## 7. Error handling & risks

- **Smaller models invent labels** → deterministic output-constraining + reject/retry; counted in eval.
- **Eval leakage** (train/eval overlap) → split before training; dedup; document in dataset card.
- **HF Jobs cost/quota** → estimate cost before launch; 4B QLoRA is cheap; cap epochs at 3.
- **`HF_TOKEN` / org not yet created** → fully parametrized via `HF_ORG`; nothing blocks design or
  local steps; publishing waits until the org + write token exist.
- **Threshold too strict/loose** → `configs/eval.yaml` is the single source of truth; tune once
  baselines are measured, record the chosen value in the model card.
- **License/attribution** → Apache-2.0; `NOTICE` credits Qwen; dataset card credits NickyNicky.
- **Qwen version drift** → pin the exact base 4B at build time; record base id + dataset hash +
  config + commit in the model-card reproducibility block.

## 8. Testing

- **Eval harness self-test:** scorer (`05_evaluate.py`) verified against a tiny hand-labeled fixture
  with known macro-F1/accuracy.
- **Dataset build test:** `01_build_dataset.py` produces valid chat JSONL, ES-only, no train/eval leakage.
- **Validation layer test:** `nebula/validation.py` correctly accepts in-set labels and rejects out-of-set.
- **CI eval-gate:** runs on PR; fails the build if the model regresses below the tier threshold.
- **Smoke:** Space `app.py` loads the GGUF and classifies an example locally before deploy.

## 9. Roadmap (after v0.1)

- **v0.2** — more Spanish tasks for Centinela (extraction/QA via EN→ES translation or synthetic);
  Centinela-8B (reasoning tier).
- **v0.3** — AWQ + vLLM serving; router 4B → 8B → frontier; k3s/ArgoCD GitOps.
- **v1.0** — full public family release with CI publish on tag.
- **Beyond** — additional families born in the Nebula (each its own `data/` + `configs/` namespace).

## 10. Naming reference

| Token | Value |
|---|---|
| Foundry / project | **Astromesh Nebula** (repo `astromesh-nebula`) |
| First family | **Centinela** (Spanish-first finance/admin) |
| First model | **Centinela-4B** (`HF_ORG/Centinela-Qwen3-4B`) |
| HF org | `HF_ORG` (= `astromesh`, to be created) |
| Base model | `Qwen/Qwen3-4B` (pin latest equivalent at build) |
| License | Apache-2.0 (inherits base) |
