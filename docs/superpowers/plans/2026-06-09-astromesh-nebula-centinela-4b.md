# Astromesh Nebula · Centinela-4B v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new sibling repo `astromesh-nebula` and ship `Centinela-Qwen3-4B` — a Spanish financial **sentiment** classifier (3 classes) — end-to-end: dataset → eval → train (HF Jobs) → quantize (GGUF) → publish to the Hugging Face Hub with a model card and a Gradio demo Space.

**Architecture:** A small testable Python library (`nebula/`) holds all pure logic — label set, deterministic output validation, metrics, dataset transform, evaluation, model-card rendering. Thin CLI scripts (`scripts/01..08`) wrap that logic for the pipeline. GPU work (train/merge/quantize) runs on **HF Jobs**; everything else runs locally and is unit-tested. The economic thesis is preserved: a tiny model + a deterministic validation layer that constrains output to the closed label set.

**Tech Stack:** Python 3.11+, `uv`, `pytest`, `ruff`, `datasets`, `huggingface_hub`, `transformers`, `peft`, `trl`/`unsloth` (training), `gradio` (demo), `llama.cpp` (GGUF). Base model `Qwen/Qwen3-4B`. Monitoring via Trackio. Apache-2.0.

**Scope note:** v0.1 narrows the Centinela task to **financial sentiment classification** (`task_type == "sentiment_analysis"`, labels `positivo / neutral / negativo`), the cleanest closed-set task with real Spanish data in `NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1` (43,830 rows, single `train` split). Topic classification, extraction, QA, the 8B model, the router, and serving are deferred per the design spec.

**Where the code lives:** A NEW git repo at `astromesh-nebula/` (sibling of `astromesh/`). All file paths in this plan are relative to that repo root unless noted. This plan document itself lives in the `astromesh` runtime repo under `docs/superpowers/plans/`.

**Canonical contracts (used across tasks — keep names exact):**
- `nebula.labels.LABELS = ["positivo", "neutral", "negativo"]`
- `nebula.labels.EN_TO_ES = {"positive": "positivo", "neutral": "neutral", "negative": "negativo"}`
- `nebula.labels.SYSTEM_PROMPT_ES` (Spanish classifier instruction)
- `nebula.validation.constrain_label(raw: str | None, labels: list[str] = LABELS) -> str | None`
- `nebula.metrics.accuracy(gold: list[str], pred: list[str | None]) -> float`
- `nebula.metrics.macro_f1(gold: list[str], pred: list[str | None], labels: list[str]) -> float`
- `nebula.metrics.classification_summary(gold, pred, labels) -> dict`
- `nebula.data.row_to_chat_record(row: dict) -> dict | None`
- `nebula.data.stratified_split(records: list[dict], eval_frac: float, seed: int) -> tuple[list[dict], list[dict]]`
- `nebula.data.record_label(record: dict) -> str` (returns the assistant message content)
- `nebula.evaluate.Classifier` (Protocol with `predict(self, text: str) -> str`)
- `nebula.evaluate.load_examples(path: str) -> list[dict]` (each `{"text": str, "gold": str}`)
- `nebula.evaluate.evaluate_classifier(clf, examples, labels) -> dict`
- `nebula.modelcard.render_model_card(**kwargs) -> str`

---

## Task 1: Scaffold the repo and tooling

**Files:**
- Create: `astromesh-nebula/pyproject.toml`
- Create: `astromesh-nebula/.gitignore`
- Create: `astromesh-nebula/.env.example`
- Create: `astromesh-nebula/nebula/__init__.py`
- Create: `astromesh-nebula/tests/__init__.py`

- [ ] **Step 1: Create the repo directory and initialize git**

Run (from `D:\monaccode`):
```bash
mkdir astromesh-nebula && cd astromesh-nebula && git init
```
Expected: `Initialized empty Git repository`.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "astromesh-nebula"
version = "0.1.0"
description = "Astromesh Nebula — open-model foundry. First family: Centinela (Spanish-first finance)."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Apache-2.0" }
dependencies = [
    "datasets>=2.19",
    "huggingface_hub>=0.24",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
eval = ["transformers>=4.44", "torch>=2.3", "accelerate>=0.33"]
demo = ["gradio>=4.0", "llama-cpp-python>=0.2.80"]
dev = ["pytest>=8.0", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["nebula"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.env
/data/*/raw/
/data/*/processed/
/checkpoints/
/export/
*.gguf
*.safetensors
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 4: Write `.env.example`**

```bash
# Hugging Face — write token for the org that will host the models/datasets/space
HF_TOKEN=
HF_ORG=astromesh
# Optional experiment tracking
WANDB_API_KEY=
```

- [ ] **Step 5: Create empty package markers**

`nebula/__init__.py`:
```python
"""Astromesh Nebula — shared library for the Centinela model family."""
```
`tests/__init__.py`:
```python
```

- [ ] **Step 6: Verify the environment installs**

Run:
```bash
uv sync --extra dev
uv run python -c "import nebula; print('ok')"
```
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example nebula/__init__.py tests/__init__.py
git commit -m "chore: scaffold astromesh-nebula repo and tooling"
```

---

## Task 2: Label set and Spanish system prompt

**Files:**
- Create: `nebula/labels.py`
- Test: `tests/test_labels.py`

- [ ] **Step 1: Write the failing test**

`tests/test_labels.py`:
```python
from nebula.labels import LABELS, EN_TO_ES, SYSTEM_PROMPT_ES


def test_label_set_is_the_three_spanish_classes():
    assert LABELS == ["positivo", "neutral", "negativo"]


def test_english_to_spanish_mapping_covers_dataset_answers():
    assert EN_TO_ES == {"positive": "positivo", "neutral": "neutral", "negative": "negativo"}
    # every mapped value must be a valid label
    assert set(EN_TO_ES.values()) == set(LABELS)


def test_system_prompt_is_spanish_and_lists_the_labels():
    p = SYSTEM_PROMPT_ES.lower()
    assert "sentimiento" in p
    for label in LABELS:
        assert label in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.labels'`.

- [ ] **Step 3: Write minimal implementation**

`nebula/labels.py`:
```python
"""Closed label set and prompt for Centinela financial sentiment classification."""

LABELS: list[str] = ["positivo", "neutral", "negativo"]

# Maps the source dataset's English answers to our Spanish-first labels.
EN_TO_ES: dict[str, str] = {
    "positive": "positivo",
    "neutral": "neutral",
    "negative": "negativo",
}

SYSTEM_PROMPT_ES: str = (
    "Sos un experto en análisis de sentimiento financiero. "
    "Analizá el sentimiento del texto financiero dado y respondé únicamente "
    "con una sola palabra: positivo, neutral o negativo."
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_labels.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add nebula/labels.py tests/test_labels.py
git commit -m "feat: add Centinela label set and Spanish system prompt"
```

---

## Task 3: Deterministic output-validation layer

**Files:**
- Create: `nebula/validation.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing test**

`tests/test_validation.py`:
```python
from nebula.validation import constrain_label


def test_exact_match_returns_label():
    assert constrain_label("positivo") == "positivo"


def test_is_case_and_whitespace_insensitive():
    assert constrain_label("  NEGATIVO\n") == "negativo"


def test_extracts_label_from_a_sentence():
    assert constrain_label("El sentimiento es claramente negativo.") == "negativo"


def test_returns_none_when_no_label_present():
    assert constrain_label("no lo sé") is None


def test_returns_none_for_none_input():
    assert constrain_label(None) is None


def test_prefers_first_occurring_label_in_text():
    # "positivo" appears before "negativo" -> positivo wins
    assert constrain_label("tono positivo, no negativo") == "positivo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.validation'`.

- [ ] **Step 3: Write minimal implementation**

`nebula/validation.py`:
```python
"""Deterministic output-constraining: map raw model text to a valid label or None.

This is the classification-flavored version of Nebula's non-negotiable rule that the
model never emits free-form answers for structured tasks. Anything outside the closed
label set is rejected (returns None) so callers can retry or count it as invalid.
"""

from nebula.labels import LABELS


def constrain_label(raw: str | None, labels: list[str] = LABELS) -> str | None:
    if not raw:
        return None
    text = raw.strip().lower()
    if text in labels:
        return text
    # Otherwise pick the label that appears earliest in the text.
    best: str | None = None
    best_pos = len(text) + 1
    for label in labels:
        pos = text.find(label)
        if 0 <= pos < best_pos:
            best, best_pos = label, pos
    return best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_validation.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add nebula/validation.py tests/test_validation.py
git commit -m "feat: add deterministic label-constraining validation layer"
```

---

## Task 4: Metrics (accuracy, macro-F1, summary)

**Files:**
- Create: `nebula/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

`tests/test_metrics.py`:
```python
from nebula.metrics import accuracy, macro_f1, classification_summary

LABELS = ["positivo", "neutral", "negativo"]


def test_accuracy_perfect():
    gold = ["positivo", "negativo", "neutral"]
    pred = ["positivo", "negativo", "neutral"]
    assert accuracy(gold, pred) == 1.0


def test_accuracy_counts_none_as_wrong():
    gold = ["positivo", "negativo"]
    pred = ["positivo", None]
    assert accuracy(gold, pred) == 0.5


def test_macro_f1_perfect_is_one():
    gold = ["positivo", "negativo", "neutral"]
    pred = ["positivo", "negativo", "neutral"]
    assert macro_f1(gold, pred, LABELS) == 1.0


def test_macro_f1_handles_a_missed_class():
    # neutral never predicted -> its F1 is 0, dragging the macro average down
    gold = ["positivo", "neutral", "negativo"]
    pred = ["positivo", "positivo", "negativo"]
    f1 = macro_f1(gold, pred, LABELS)
    assert 0.0 < f1 < 1.0


def test_summary_reports_invalid_rate():
    gold = ["positivo", "negativo"]
    pred = ["positivo", None]
    summary = classification_summary(gold, pred, LABELS)
    assert summary["accuracy"] == 0.5
    assert summary["invalid_rate"] == 0.5
    assert "macro_f1" in summary
    assert set(summary["per_label"].keys()) == set(LABELS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.metrics'`.

- [ ] **Step 3: Write minimal implementation**

`nebula/metrics.py`:
```python
"""Classification metrics over (gold, pred) lists. `pred` may contain None (invalid)."""


def accuracy(gold: list[str], pred: list[str | None]) -> float:
    if not gold:
        return 0.0
    correct = sum(1 for g, p in zip(gold, pred) if p is not None and g == p)
    return correct / len(gold)


def _f1_for_label(gold: list[str], pred: list[str | None], label: str) -> float:
    tp = sum(1 for g, p in zip(gold, pred) if p == label and g == label)
    fp = sum(1 for g, p in zip(gold, pred) if p == label and g != label)
    fn = sum(1 for g, p in zip(gold, pred) if p != label and g == label)
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def macro_f1(gold: list[str], pred: list[str | None], labels: list[str]) -> float:
    if not labels:
        return 0.0
    return sum(_f1_for_label(gold, pred, lab) for lab in labels) / len(labels)


def classification_summary(
    gold: list[str], pred: list[str | None], labels: list[str]
) -> dict:
    invalid = sum(1 for p in pred if p is None)
    return {
        "n": len(gold),
        "accuracy": accuracy(gold, pred),
        "macro_f1": macro_f1(gold, pred, labels),
        "invalid_rate": invalid / len(gold) if gold else 0.0,
        "per_label": {lab: _f1_for_label(gold, pred, lab) for lab in labels},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add nebula/metrics.py tests/test_metrics.py
git commit -m "feat: add classification metrics with invalid-rate tracking"
```

---

## Task 5: Dataset transform and stratified split

**Files:**
- Create: `nebula/data.py`
- Test: `tests/test_data.py`

- [ ] **Step 1: Write the failing test**

`tests/test_data.py`:
```python
from nebula.data import row_to_chat_record, stratified_split, record_label
from nebula.labels import SYSTEM_PROMPT_ES


def _row(es, answer, task="sentiment_analysis"):
    return {
        "user_prompt_en": "ignored",
        "user_prompt_es": es,
        "answer": answer,
        "system_prompt": "ignored english prompt",
        "task_type": task,
    }


def test_row_maps_to_spanish_chat_record():
    rec = row_to_chat_record(_row("La acción subió fuerte.", "positive"))
    assert rec["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT_ES}
    assert rec["messages"][1] == {"role": "user", "content": "La acción subió fuerte."}
    assert rec["messages"][2] == {"role": "assistant", "content": "positivo"}


def test_row_skips_non_sentiment_tasks():
    assert row_to_chat_record(_row("texto", "positive", task="topic_classification")) is None


def test_row_skips_unknown_answer():
    assert row_to_chat_record(_row("texto", "mixed")) is None


def test_row_skips_empty_spanish_text():
    assert row_to_chat_record(_row("   ", "positive")) is None


def test_record_label_returns_assistant_content():
    rec = row_to_chat_record(_row("texto", "negative"))
    assert record_label(rec) == "negativo"


def test_stratified_split_is_deterministic_and_balanced():
    records = []
    for i in range(30):
        ans = ["positive", "neutral", "negative"][i % 3]
        records.append(row_to_chat_record(_row(f"texto {i}", ans)))
    train1, eval1 = stratified_split(records, eval_frac=0.2, seed=42)
    train2, eval2 = stratified_split(records, eval_frac=0.2, seed=42)
    # deterministic
    assert [record_label(r) for r in eval1] == [record_label(r) for r in eval2]
    # ~20% held out, every class represented in eval
    assert len(eval1) == 6
    assert {record_label(r) for r in eval1} == {"positivo", "neutral", "negativo"}
    # no leakage: no eval text appears in train
    train_texts = {r["messages"][1]["content"] for r in train1}
    eval_texts = {r["messages"][1]["content"] for r in eval1}
    assert train_texts.isdisjoint(eval_texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.data'`.

- [ ] **Step 3: Write minimal implementation**

`nebula/data.py`:
```python
"""Transform source rows into Spanish chat records and split them deterministically."""

import random
from collections import defaultdict

from nebula.labels import EN_TO_ES, SYSTEM_PROMPT_ES


def row_to_chat_record(row: dict) -> dict | None:
    if row.get("task_type") != "sentiment_analysis":
        return None
    answer = (row.get("answer") or "").strip().lower()
    if answer not in EN_TO_ES:
        return None
    text = (row.get("user_prompt_es") or "").strip()
    if not text:
        return None
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_ES},
            {"role": "user", "content": text},
            {"role": "assistant", "content": EN_TO_ES[answer]},
        ]
    }


def record_label(record: dict) -> str:
    return record["messages"][2]["content"]


def stratified_split(
    records: list[dict], eval_frac: float, seed: int
) -> tuple[list[dict], list[dict]]:
    by_label: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_label[record_label(rec)].append(rec)

    rng = random.Random(seed)
    train: list[dict] = []
    eval_set: list[dict] = []
    for label in sorted(by_label):
        group = by_label[label][:]
        rng.shuffle(group)
        n_eval = round(len(group) * eval_frac)
        eval_set.extend(group[:n_eval])
        train.extend(group[n_eval:])
    rng.shuffle(train)
    rng.shuffle(eval_set)
    return train, eval_set
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add nebula/data.py tests/test_data.py
git commit -m "feat: add dataset transform and stratified split"
```

---

## Task 6: Evaluation harness (Classifier protocol + scorer)

**Files:**
- Create: `nebula/evaluate.py`
- Test: `tests/test_evaluate.py`

- [ ] **Step 1: Write the failing test**

`tests/test_evaluate.py`:
```python
import json

from nebula.evaluate import load_examples, evaluate_classifier
from nebula.labels import LABELS


class FakeClassifier:
    """Returns canned raw outputs in order; lets us test scoring without a model."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self._i = 0

    def predict(self, text: str) -> str:
        out = self._outputs[self._i]
        self._i += 1
        return out


def test_load_examples_reads_eval_jsonl(tmp_path):
    path = tmp_path / "eval.jsonl"
    rec = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "La bolsa cae."},
            {"role": "assistant", "content": "negativo"},
        ]
    }
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    examples = load_examples(str(path))
    assert examples == [{"text": "La bolsa cae.", "gold": "negativo"}]


def test_evaluate_classifier_scores_and_constrains():
    examples = [
        {"text": "sube", "gold": "positivo"},
        {"text": "cae", "gold": "negativo"},
        {"text": "estable", "gold": "neutral"},
    ]
    # raw outputs: a sentence (constrained to positivo), exact, and garbage (-> invalid)
    clf = FakeClassifier(["es positivo", "negativo", "no sé"])
    result = evaluate_classifier(clf, examples, LABELS)
    assert result["n"] == 3
    assert result["accuracy"] == 2 / 3
    assert result["invalid_rate"] == 1 / 3
    assert result["predictions"] == ["positivo", "negativo", None]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.evaluate'`.

- [ ] **Step 3: Write minimal implementation**

`nebula/evaluate.py`:
```python
"""Evaluation harness: run a Classifier over eval examples and score it."""

import json
from typing import Protocol

from nebula.metrics import classification_summary
from nebula.validation import constrain_label


class Classifier(Protocol):
    def predict(self, text: str) -> str: ...


def load_examples(path: str) -> list[dict]:
    examples: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            messages = json.loads(line)["messages"]
            text = next(m["content"] for m in messages if m["role"] == "user")
            gold = next(m["content"] for m in messages if m["role"] == "assistant")
            examples.append({"text": text, "gold": gold})
    return examples


def evaluate_classifier(clf: Classifier, examples: list[dict], labels: list[str]) -> dict:
    gold = [ex["gold"] for ex in examples]
    pred = [constrain_label(clf.predict(ex["text"]), labels) for ex in examples]
    summary = classification_summary(gold, pred, labels)
    summary["predictions"] = pred
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add nebula/evaluate.py tests/test_evaluate.py
git commit -m "feat: add evaluation harness with Classifier protocol"
```

---

## Task 7: Model-card renderer

**Files:**
- Create: `nebula/modelcard.py`
- Test: `tests/test_modelcard.py`

- [ ] **Step 1: Write the failing test**

`tests/test_modelcard.py`:
```python
from nebula.modelcard import render_model_card


def test_render_model_card_has_yaml_header_and_injected_eval():
    card = render_model_card(
        repo_id="astromesh/Centinela-Qwen3-4B",
        base_model="Qwen/Qwen3-4B",
        dataset_id="NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1",
        eval_table="| Metric | Base | Centinela-4B |\n|---|---|---|\n| macro-F1 | 0.61 | 0.88 |",
        n_train=1000,
        n_eval=250,
        base_model_id="Qwen/Qwen3-4B",
        dataset_hash="abc123",
        config_path="configs/train-4b.yaml",
        commit="deadbeef",
    )
    assert card.startswith("---\n")
    assert "license: apache-2.0" in card
    assert "base_model: Qwen/Qwen3-4B" in card
    assert "language:" in card
    assert "pipeline_tag: text-generation" in card
    assert "macro-F1 | 0.61 | 0.88" in card
    assert "abc123" in card  # reproducibility block
    assert "deadbeef" in card
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_modelcard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.modelcard'`.

- [ ] **Step 3: Write minimal implementation**

`nebula/modelcard.py`:
```python
"""Render the Hugging Face model card (README.md) for a Centinela model."""

_TEMPLATE = """---
license: apache-2.0
base_model: {base_model}
language: [es, en]
pipeline_tag: text-generation
library_name: peft
tags: [finance, sentiment, spanish, latam, qlora, astromesh, nebula, centinela]
datasets: [{dataset_id}]
---

# {repo_id}

Spanish-first financial **sentiment** classifier (positivo / neutral / negativo).
First model of the **Centinela** family, born in the **Astromesh Nebula** open-model foundry.
Designed for low-cost, self-hosted agents.

## Intended use
Classify the sentiment of Spanish financial text into `positivo`, `neutral`, or `negativo`.
Outputs are constrained to that closed set by a deterministic validation layer.
NOT a substitute for a licensed accountant or financial advisor.

## How to use
transformers / Ollama (GGUF). See the repo quickstart.

## Training
- Method: QLoRA (4-bit) on `{base_model}`
- Data: {n_train} Spanish examples (eval held out: {n_eval}) from `{dataset_id}`

## Evaluation
{eval_table}

## Reproducibility
base_model: {base_model_id} · dataset_hash: {dataset_hash} · config: {config_path} · commit: {commit}

## Limitations & risks
Spanish-optimized; may misclassify domain-shifted text. Always validate before acting on outputs.
Not for autonomous high-stakes financial decisions.

## License
Apache-2.0, inheriting the base model license.
"""


def render_model_card(
    *,
    repo_id: str,
    base_model: str,
    dataset_id: str,
    eval_table: str,
    n_train: int,
    n_eval: int,
    base_model_id: str,
    dataset_hash: str,
    config_path: str,
    commit: str,
) -> str:
    return _TEMPLATE.format(
        repo_id=repo_id,
        base_model=base_model,
        dataset_id=dataset_id,
        eval_table=eval_table,
        n_train=n_train,
        n_eval=n_eval,
        base_model_id=base_model_id,
        dataset_hash=dataset_hash,
        config_path=config_path,
        commit=commit,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_modelcard.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add nebula/modelcard.py tests/test_modelcard.py
git commit -m "feat: add model-card renderer"
```

---

## Task 8: Configs (`configs/eval.yaml`, `configs/train-4b.yaml`)

**Files:**
- Create: `configs/eval.yaml`
- Create: `configs/train-4b.yaml`
- Create: `nebula/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from nebula.config import load_eval_config, load_train_config


def test_eval_config_has_threshold_and_labels():
    cfg = load_eval_config("configs/eval.yaml")
    assert cfg["task"] == "sentiment_analysis"
    assert cfg["labels"] == ["positivo", "neutral", "negativo"]
    assert cfg["thresholds"]["macro_f1"] == 0.85
    assert cfg["thresholds"]["must_beat_base"] is True


def test_train_config_has_qlora_hyperparams():
    cfg = load_train_config("configs/train-4b.yaml")
    assert cfg["base_model"] == "Qwen/Qwen3-4B"
    assert cfg["lora"]["r"] == 16
    assert cfg["lora"]["alpha"] == 16
    assert cfg["train"]["learning_rate"] == 2e-4
    assert 1 <= cfg["train"]["epochs"] <= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nebula.config'`.

- [ ] **Step 3: Write the configs and loader**

`configs/eval.yaml`:
```yaml
task: sentiment_analysis
labels: [positivo, neutral, negativo]
eval_path: data/centinela/eval.jsonl
thresholds:
  macro_f1: 0.85       # initial target; tune after baselines are measured
  must_beat_base: true # Centinela-4B must strictly beat base Qwen3-4B few-shot
```

`configs/train-4b.yaml`:
```yaml
base_model: Qwen/Qwen3-4B
output_repo: Centinela-Qwen3-4B      # joined with HF_ORG at publish time
train_path: data/centinela/train.jsonl
max_seq_length: 1024
lora:
  r: 16
  alpha: 16
  dropout: 0.0
  target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]
train:
  epochs: 2
  learning_rate: 2.0e-4
  per_device_batch_size: 8
  gradient_accumulation_steps: 2
  gradient_checkpointing: true
  seed: 42
```

`nebula/config.py`:
```python
"""Load YAML configs for evaluation and training."""

import yaml


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_eval_config(path: str) -> dict:
    return _load(path)


def load_train_config(path: str) -> dict:
    return _load(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add configs/eval.yaml configs/train-4b.yaml nebula/config.py tests/test_config.py
git commit -m "feat: add eval and train-4b configs with loader"
```

---

## Task 9: `scripts/01_build_dataset.py` (build JSONL + labels + dataset card)

**Files:**
- Create: `scripts/01_build_dataset.py`
- Create: `data/centinela/README.md`
- Test: `tests/test_build_dataset.py`

- [ ] **Step 1: Write the failing test**

The script's heavy lifting lives in `nebula/data.py` (already tested). Here we test the
file-writing helper `build_split_files`, which the CLI calls. Add it to the test target.

`tests/test_build_dataset.py`:
```python
import json
import importlib.util
from pathlib import Path

# load the numbered script as a module
spec = importlib.util.spec_from_file_location(
    "build_dataset", str(Path("scripts/01_build_dataset.py"))
)
build_dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_dataset)


def test_build_split_files_writes_jsonl_and_labels(tmp_path):
    rows = []
    for i in range(30):
        ans = ["positive", "neutral", "negative"][i % 3]
        rows.append(
            {
                "user_prompt_es": f"texto financiero {i}",
                "answer": ans,
                "task_type": "sentiment_analysis",
            }
        )
    out_dir = tmp_path / "centinela"
    stats = build_dataset.build_split_files(rows, str(out_dir), eval_frac=0.2, seed=42)

    train_lines = (out_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()
    eval_lines = (out_dir / "eval.jsonl").read_text(encoding="utf-8").splitlines()
    labels = json.loads((out_dir / "labels.json").read_text(encoding="utf-8"))

    assert len(train_lines) == stats["n_train"]
    assert len(eval_lines) == stats["n_eval"]
    assert stats["n_train"] + stats["n_eval"] == 30
    assert labels == ["positivo", "neutral", "negativo"]
    # every line is a valid chat record
    rec = json.loads(train_lines[0])
    assert rec["messages"][0]["role"] == "system"
    # no leakage between splits
    train_texts = {json.loads(l)["messages"][1]["content"] for l in train_lines}
    eval_texts = {json.loads(l)["messages"][1]["content"] for l in eval_lines}
    assert train_texts.isdisjoint(eval_texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build_dataset.py -v`
Expected: FAIL — `scripts/01_build_dataset.py` does not exist (spec load error).

- [ ] **Step 3: Write the script**

`scripts/01_build_dataset.py`:
```python
"""Build Centinela's Spanish sentiment dataset from the NickyNicky source.

Usage:
    uv run python scripts/01_build_dataset.py \
        --dataset NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1 \
        --out data/centinela --eval-frac 0.2 --seed 42
"""

import argparse
import hashlib
import json
import os

from nebula.data import record_label, row_to_chat_record, stratified_split
from nebula.labels import LABELS


def build_split_files(rows, out_dir: str, eval_frac: float, seed: int) -> dict:
    records = [r for r in (row_to_chat_record(row) for row in rows) if r is not None]
    # dedup by Spanish text to prevent leakage from duplicate source rows
    seen: set[str] = set()
    deduped = []
    for rec in records:
        text = rec["messages"][1]["content"]
        if text not in seen:
            seen.add(text)
            deduped.append(rec)

    train, eval_set = stratified_split(deduped, eval_frac=eval_frac, seed=seed)

    os.makedirs(out_dir, exist_ok=True)
    _write_jsonl(os.path.join(out_dir, "train.jsonl"), train)
    _write_jsonl(os.path.join(out_dir, "eval.jsonl"), eval_set)
    with open(os.path.join(out_dir, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump(LABELS, fh, ensure_ascii=False)

    digest = _hash_records(train + eval_set)
    return {
        "n_train": len(train),
        "n_eval": len(eval_set),
        "dataset_hash": digest,
        "label_counts": _label_counts(deduped),
    }


def _write_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _label_counts(records: list[dict]) -> dict:
    counts: dict[str, int] = {lab: 0 for lab in LABELS}
    for rec in records:
        counts[record_label(rec)] += 1
    return counts


def _hash_records(records: list[dict]) -> str:
    h = hashlib.sha256()
    for rec in records:
        h.update(json.dumps(rec, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:12]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default="data/centinela")
    ap.add_argument("--eval-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    from datasets import load_dataset

    ds = load_dataset(args.dataset, split="train")
    stats = build_split_files(
        list(ds), args.out, eval_frac=args.eval_frac, seed=args.seed
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_build_dataset.py -v`
Expected: 1 passed.

- [ ] **Step 5: Write the dataset card**

`data/centinela/README.md`:
```markdown
# Centinela sentiment dataset (processed)

Spanish financial sentiment classification, derived from
[`NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1`](https://huggingface.co/datasets/NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1)
(Apache-2.0). We keep only `task_type == sentiment_analysis`, use the Spanish text
(`user_prompt_es`), and map answers to Spanish labels (`positivo`/`neutral`/`negativo`).

- Format: chat JSONL (`messages` with system/user/assistant).
- Split: stratified by label, seed 42, eval fraction 0.2, deduplicated by text (no leakage).
- PII: none (public source).
- Build: `uv run python scripts/01_build_dataset.py --dataset <id> --out data/centinela`.
```

- [ ] **Step 6: Run the real build once (integration, needs network)**

Run:
```bash
uv sync --extra eval
uv run python scripts/01_build_dataset.py \
  --dataset NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1 \
  --out data/centinela
```
Expected: prints stats JSON with `n_train`, `n_eval`, `dataset_hash`, `label_counts`;
creates `data/centinela/train.jsonl`, `eval.jsonl`, `labels.json` (gitignored).

- [ ] **Step 7: Commit**

```bash
git add scripts/01_build_dataset.py data/centinela/README.md tests/test_build_dataset.py
git commit -m "feat: add dataset build script and dataset card"
```

---

## Task 10: `scripts/05_evaluate.py` (CLI: base vs Centinela-4B)

**Files:**
- Create: `scripts/05_evaluate.py`
- Create: `nebula/hf_classifier.py`
- Test: `tests/test_evaluate_cli.py`

- [ ] **Step 1: Write the failing test**

We test `format_results_table` (pure) and `gate_passes` (pure). The model-backed classifier
(`nebula/hf_classifier.py`) is exercised only in the integration run (Step 6), not unit-tested.

`tests/test_evaluate_cli.py`:
```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "evaluate_cli", str(Path("scripts/05_evaluate.py"))
)
evaluate_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate_cli)


def test_format_results_table_includes_both_columns():
    base = {"accuracy": 0.61, "macro_f1": 0.60, "invalid_rate": 0.10}
    tuned = {"accuracy": 0.90, "macro_f1": 0.88, "invalid_rate": 0.0}
    table = evaluate_cli.format_results_table(base, tuned)
    assert "macro-F1" in table
    assert "0.60" in table and "0.88" in table
    assert "Base" in table and "Centinela-4B" in table


def test_gate_passes_requires_threshold_and_beating_base():
    base = {"macro_f1": 0.60}
    tuned_good = {"macro_f1": 0.88}
    tuned_bad = {"macro_f1": 0.80}
    assert evaluate_cli.gate_passes(tuned_good, base, threshold=0.85, must_beat_base=True)
    assert not evaluate_cli.gate_passes(tuned_bad, base, threshold=0.85, must_beat_base=True)
    # beats base but below threshold -> still fails
    assert not evaluate_cli.gate_passes({"macro_f1": 0.70}, base, threshold=0.85, must_beat_base=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluate_cli.py -v`
Expected: FAIL — `scripts/05_evaluate.py` does not exist.

- [ ] **Step 3: Write the HF classifier and the CLI**

`nebula/hf_classifier.py`:
```python
"""A Classifier backed by a transformers chat model (used at eval/integration time)."""

from nebula.labels import SYSTEM_PROMPT_ES


class HFChatClassifier:
    def __init__(self, model_id: str, max_new_tokens: int = 8):
        from transformers import pipeline

        self._pipe = pipeline("text-generation", model=model_id, device_map="auto")
        self._max_new_tokens = max_new_tokens

    def predict(self, text: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_ES},
            {"role": "user", "content": text},
        ]
        out = self._pipe(
            messages, max_new_tokens=self._max_new_tokens, do_sample=False
        )
        generated = out[0]["generated_text"]
        # transformers returns the full conversation; take the last assistant turn
        if isinstance(generated, list):
            return generated[-1]["content"]
        return str(generated)
```

`scripts/05_evaluate.py`:
```python
"""Evaluate base Qwen3-4B vs Centinela-4B on the held-out Spanish eval set.

Usage:
    uv run python scripts/05_evaluate.py \
        --base Qwen/Qwen3-4B --tuned ./export/merged \
        --eval data/centinela/eval.jsonl --out eval/results/results.md
"""

import argparse
import os

from nebula.config import load_eval_config
from nebula.evaluate import evaluate_classifier, load_examples
from nebula.labels import LABELS


def format_results_table(base: dict, tuned: dict) -> str:
    rows = [
        ("accuracy", "accuracy"),
        ("macro-F1", "macro_f1"),
        ("invalid rate", "invalid_rate"),
    ]
    lines = ["| Metric | Base | Centinela-4B |", "|---|---|---|"]
    for label, key in rows:
        lines.append(f"| {label} | {base[key]:.2f} | {tuned[key]:.2f} |")
    return "\n".join(lines)


def gate_passes(tuned: dict, base: dict, threshold: float, must_beat_base: bool) -> bool:
    if tuned["macro_f1"] < threshold:
        return False
    if must_beat_base and tuned["macro_f1"] <= base["macro_f1"]:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--tuned", required=True)
    ap.add_argument("--eval", default="data/centinela/eval.jsonl")
    ap.add_argument("--config", default="configs/eval.yaml")
    ap.add_argument("--out", default="eval/results/results.md")
    ap.add_argument("--frontier", action="store_true", help="(disabled in v0.1)")
    args = ap.parse_args()

    from nebula.hf_classifier import HFChatClassifier

    cfg = load_eval_config(args.config)
    examples = load_examples(args.eval)

    base_res = evaluate_classifier(HFChatClassifier(args.base), examples, LABELS)
    tuned_res = evaluate_classifier(HFChatClassifier(args.tuned), examples, LABELS)

    table = format_results_table(base_res, tuned_res)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("# Centinela-4B evaluation\n\n" + table + "\n")

    passed = gate_passes(
        tuned_res,
        base_res,
        threshold=cfg["thresholds"]["macro_f1"],
        must_beat_base=cfg["thresholds"]["must_beat_base"],
    )
    print(table)
    print(f"\nGATE: {'PASS' if passed else 'FAIL'}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluate_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full unit suite and lint**

Run:
```bash
uv run pytest -v
uv run ruff check nebula/ tests/ scripts/
```
Expected: all tests pass; ruff reports no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/05_evaluate.py nebula/hf_classifier.py tests/test_evaluate_cli.py
git commit -m "feat: add evaluation CLI with tier gate"
```

---

## Task 11: Training, merge, quantize scripts (HF Jobs)

These run on GPU via HF Jobs and cannot be unit-tested in CI. Each is delivered as a runnable
script plus a local **import/parse smoke test** and an exact launch command. GPU execution is a
manual integration step.

**Files:**
- Create: `scripts/02_train.py`
- Create: `scripts/03_merge.py`
- Create: `scripts/04_quantize.sh`
- Test: `tests/test_scripts_smoke.py`

- [ ] **Step 1: Write the smoke test**

`tests/test_scripts_smoke.py`:
```python
import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("path", ["scripts/02_train.py", "scripts/03_merge.py"])
def test_script_is_valid_python(path):
    src = Path(path).read_text(encoding="utf-8")
    ast.parse(src)  # raises SyntaxError if malformed


def test_quantize_script_targets_q4_k_m():
    src = Path("scripts/04_quantize.sh").read_text(encoding="utf-8")
    assert "Q4_K_M" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scripts_smoke.py -v`
Expected: FAIL — the script files do not exist.

- [ ] **Step 3: Write `scripts/02_train.py`**

A self-contained UV script (PEP 723 inline deps) suitable for `hf jobs uv run`.

`scripts/02_train.py`:
```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "unsloth",
#   "trl>=0.9",
#   "transformers>=4.44",
#   "datasets>=2.19",
#   "pyyaml>=6.0",
#   "huggingface_hub>=0.24",
# ]
# ///
"""QLoRA fine-tune Qwen3-4B on the Centinela Spanish sentiment dataset.

Run locally (GPU) or on HF Jobs:
    hf jobs uv run --flavor a10g-large scripts/02_train.py -- \
        --config configs/train-4b.yaml --train data/centinela/train.jsonl \
        --out export/adapter
"""

import argparse
import json

import yaml
from datasets import load_dataset
from trl import SFTConfig, SFTTrainer
from unsloth import FastLanguageModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/train-4b.yaml")
    ap.add_argument("--train", default="data/centinela/train.jsonl")
    ap.add_argument("--out", default="export/adapter")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=cfg["base_model"],
        max_seq_length=cfg["max_seq_length"],
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["alpha"],
        lora_dropout=cfg["lora"]["dropout"],
        target_modules=cfg["lora"]["target_modules"],
        use_gradient_checkpointing=cfg["train"]["gradient_checkpointing"],
    )

    dataset = load_dataset("json", data_files=args.train, split="train")

    def formatting(example):
        return tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        formatting_func=formatting,
        args=SFTConfig(
            output_dir="checkpoints",
            num_train_epochs=cfg["train"]["epochs"],
            learning_rate=cfg["train"]["learning_rate"],
            per_device_train_batch_size=cfg["train"]["per_device_batch_size"],
            gradient_accumulation_steps=cfg["train"]["gradient_accumulation_steps"],
            seed=cfg["train"]["seed"],
            max_seq_length=cfg["max_seq_length"],
            logging_steps=10,
        ),
    )
    trainer.train()
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print(json.dumps({"adapter": args.out, "base_model": cfg["base_model"]}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `scripts/03_merge.py`**

`scripts/03_merge.py`:
```python
"""Merge a LoRA adapter into the base model and save bf16 safetensors.

    uv run python scripts/03_merge.py --base Qwen/Qwen3-4B \
        --adapter export/adapter --out export/merged
"""

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", default="export/merged")
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(base, args.adapter)
    model = model.merge_and_unload()
    model.save_pretrained(args.out, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base).save_pretrained(args.out)
    print(f"merged -> {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Write `scripts/04_quantize.sh`**

`scripts/04_quantize.sh`:
```bash
#!/usr/bin/env bash
# Quantize merged bf16 weights to GGUF Q4_K_M using llama.cpp.
# Usage: scripts/04_quantize.sh export/merged export/centinela-4b.Q4_K_M.gguf
set -euo pipefail

MERGED="${1:-export/merged}"
OUT="${2:-export/centinela-4b.Q4_K_M.gguf}"
LLAMA_CPP="${LLAMA_CPP:-./llama.cpp}"

if [ ! -d "$LLAMA_CPP" ]; then
  git clone https://github.com/ggerganov/llama.cpp "$LLAMA_CPP"
  pip install -r "$LLAMA_CPP/requirements.txt"
fi

python "$LLAMA_CPP/convert_hf_to_gguf.py" "$MERGED" --outfile export/centinela-4b.f16.gguf --outtype f16
"$LLAMA_CPP/llama-quantize" export/centinela-4b.f16.gguf "$OUT" Q4_K_M

echo "wrote $OUT"
```

- [ ] **Step 6: Run smoke tests**

Run: `uv run pytest tests/test_scripts_smoke.py -v`
Expected: 3 passed.

- [ ] **Step 7: (Integration, manual/cloud) launch training on HF Jobs**

Run (requires `HF_TOKEN` and org access):
```bash
hf auth login
hf jobs uv run --flavor a10g-large scripts/02_train.py -- \
  --config configs/train-4b.yaml --train data/centinela/train.jsonl --out export/adapter
```
Expected: a finished job with the adapter saved. Then run `03_merge.py` and `04_quantize.sh`
(locally on a GPU box or as follow-up jobs). Record the produced `dataset_hash` and base id.

- [ ] **Step 8: Commit**

```bash
git add scripts/02_train.py scripts/03_merge.py scripts/04_quantize.sh tests/test_scripts_smoke.py
git commit -m "feat: add QLoRA train, merge, and GGUF quantize scripts"
```

---

## Task 12: `scripts/06_push_to_hub.py` (publish model + card + tag)

**Files:**
- Create: `scripts/06_push_to_hub.py`
- Test: `tests/test_push_to_hub.py`

- [ ] **Step 1: Write the failing test**

We test `publish` against a fake HF API object, asserting the right calls happen and the card
is rendered and written. No network.

`tests/test_push_to_hub.py`:
```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "push_to_hub", str(Path("scripts/06_push_to_hub.py"))
)
push_to_hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push_to_hub)


class FakeApi:
    def __init__(self):
        self.calls = []

    def create_repo(self, **kw):
        self.calls.append(("create_repo", kw))

    def upload_folder(self, **kw):
        self.calls.append(("upload_folder", kw))

    def upload_file(self, **kw):
        self.calls.append(("upload_file", kw))

    def create_tag(self, *a, **kw):
        self.calls.append(("create_tag", {"args": a, **kw}))


def test_publish_creates_repo_uploads_and_tags(tmp_path):
    # minimal artifact dirs
    (tmp_path / "merged").mkdir()
    (tmp_path / "adapter").mkdir()
    gguf = tmp_path / "model.Q4_K_M.gguf"
    gguf.write_bytes(b"gguf")
    results = tmp_path / "results.md"
    results.write_text("| macro-F1 | 0.61 | 0.88 |", encoding="utf-8")

    api = FakeApi()
    card_path = tmp_path / "card.md"
    push_to_hub.publish(
        api=api,
        repo_id="astromesh/Centinela-Qwen3-4B",
        merged_dir=str(tmp_path / "merged"),
        adapter_dir=str(tmp_path / "adapter"),
        gguf_path=str(gguf),
        eval_table_path=str(results),
        card_out=str(card_path),
        tag="v0.1",
        base_model="Qwen/Qwen3-4B",
        dataset_id="NickyNicky/...",
        n_train=1000,
        n_eval=250,
        dataset_hash="abc123",
        commit="deadbeef",
    )

    names = [c[0] for c in api.calls]
    assert names.count("create_repo") == 1
    assert "upload_folder" in names
    assert "upload_file" in names
    assert "create_tag" in names
    # card rendered and written
    card = card_path.read_text(encoding="utf-8")
    assert "license: apache-2.0" in card
    assert "0.88" in card
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_push_to_hub.py -v`
Expected: FAIL — `scripts/06_push_to_hub.py` does not exist.

- [ ] **Step 3: Write the script**

`scripts/06_push_to_hub.py`:
```python
"""Publish a Centinela model to the Hugging Face Hub: artifacts + card + tag.

    uv run python scripts/06_push_to_hub.py --size 4b --tag v0.1
"""

import argparse
import os

from nebula.modelcard import render_model_card


def publish(
    *,
    api,
    repo_id: str,
    merged_dir: str,
    adapter_dir: str,
    gguf_path: str,
    eval_table_path: str,
    card_out: str,
    tag: str,
    base_model: str,
    dataset_id: str,
    n_train: int,
    n_eval: int,
    dataset_hash: str,
    commit: str,
) -> None:
    api.create_repo(repo_id=repo_id, repo_type="model", private=False, exist_ok=True)
    api.upload_folder(repo_id=repo_id, folder_path=merged_dir)
    api.upload_folder(repo_id=repo_id, folder_path=adapter_dir, path_in_repo="adapter")
    api.upload_file(
        repo_id=repo_id,
        path_or_fileobj=gguf_path,
        path_in_repo=f"gguf/{os.path.basename(gguf_path)}",
    )

    with open(eval_table_path, encoding="utf-8") as fh:
        eval_table = fh.read().strip()

    card = render_model_card(
        repo_id=repo_id,
        base_model=base_model,
        dataset_id=dataset_id,
        eval_table=eval_table,
        n_train=n_train,
        n_eval=n_eval,
        base_model_id=base_model,
        dataset_hash=dataset_hash,
        config_path="configs/train-4b.yaml",
        commit=commit,
    )
    with open(card_out, "w", encoding="utf-8") as fh:
        fh.write(card)
    api.upload_file(repo_id=repo_id, path_or_fileobj=card_out, path_in_repo="README.md")
    api.create_tag(repo_id, tag=tag, repo_type="model")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="4b")
    ap.add_argument("--tag", default="v0.1")
    ap.add_argument("--merged", default="export/merged")
    ap.add_argument("--adapter", default="export/adapter")
    ap.add_argument("--gguf", default="export/centinela-4b.Q4_K_M.gguf")
    ap.add_argument("--eval-table", default="eval/results/results.md")
    ap.add_argument("--dataset-hash", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--n-train", type=int, required=True)
    ap.add_argument("--n-eval", type=int, required=True)
    args = ap.parse_args()

    from huggingface_hub import HfApi

    org = os.environ["HF_ORG"]
    dataset_id = (
        "NickyNicky/Finance_sentiment_and_topic_classification_"
        "Translation_English_to_Spanish_v1"
    )
    publish(
        api=HfApi(token=os.environ["HF_TOKEN"]),
        repo_id=f"{org}/Centinela-Qwen3-{args.size.upper()}",
        merged_dir=args.merged,
        adapter_dir=args.adapter,
        gguf_path=args.gguf,
        eval_table_path=args.eval_table,
        card_out="model_card/Centinela-4B.md",
        tag=args.tag,
        base_model="Qwen/Qwen3-4B",
        dataset_id=dataset_id,
        n_train=args.n_train,
        n_eval=args.n_eval,
        dataset_hash=args.dataset_hash,
        commit=args.commit,
    )
    print(f"published {org}/Centinela-Qwen3-{args.size.upper()} @ {args.tag}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_push_to_hub.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/06_push_to_hub.py tests/test_push_to_hub.py
git commit -m "feat: add HF Hub publish script with model card + tag"
```

---

## Task 13: `scripts/07_publish_dataset.py` (publish processed ES split)

**Files:**
- Create: `scripts/07_publish_dataset.py`
- Test: `tests/test_publish_dataset.py`

- [ ] **Step 1: Write the failing test**

`tests/test_publish_dataset.py`:
```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "publish_dataset", str(Path("scripts/07_publish_dataset.py"))
)
publish_dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_dataset)


class FakeApi:
    def __init__(self):
        self.calls = []

    def create_repo(self, **kw):
        self.calls.append(("create_repo", kw))

    def upload_folder(self, **kw):
        self.calls.append(("upload_folder", kw))


def test_publish_dataset_creates_dataset_repo_and_uploads(tmp_path):
    data_dir = tmp_path / "centinela"
    data_dir.mkdir()
    (data_dir / "train.jsonl").write_text("{}", encoding="utf-8")
    (data_dir / "README.md").write_text("card", encoding="utf-8")

    api = FakeApi()
    publish_dataset.publish_dataset(
        api=api, repo_id="astromesh/centinela-sentiment-es", data_dir=str(data_dir)
    )
    names = [c[0] for c in api.calls]
    assert names == ["create_repo", "upload_folder"]
    assert api.calls[0][1]["repo_type"] == "dataset"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish_dataset.py -v`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Write the script**

`scripts/07_publish_dataset.py`:
```python
"""Publish the processed Spanish split + dataset card (public source, no PII).

    uv run python scripts/07_publish_dataset.py --repo astromesh/centinela-sentiment-es
"""

import argparse
import os


def publish_dataset(*, api, repo_id: str, data_dir: str) -> None:
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)
    api.upload_folder(repo_id=repo_id, repo_type="dataset", folder_path=data_dir)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--data-dir", default="data/centinela")
    args = ap.parse_args()

    from huggingface_hub import HfApi

    publish_dataset(
        api=HfApi(token=os.environ["HF_TOKEN"]),
        repo_id=args.repo,
        data_dir=args.data_dir,
    )
    print(f"published dataset {args.repo}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_publish_dataset.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/07_publish_dataset.py tests/test_publish_dataset.py
git commit -m "feat: add dataset publish script"
```

---

## Task 14: Gradio demo Space + deploy script

**Files:**
- Create: `demo/app.py`
- Create: `demo/requirements.txt`
- Create: `demo/README.md`
- Create: `scripts/08_deploy_space.py`
- Test: `tests/test_demo_app.py`

- [ ] **Step 1: Write the failing test**

We test the pure `classify_text(raw_output)` helper in `demo/app.py` (the model call is mocked
out behind a module-level `_predict` function the test overrides).

`tests/test_demo_app.py`:
```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("demo_app", str(Path("demo/app.py")))
demo_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo_app)


def test_classify_text_constrains_output(monkeypatch):
    monkeypatch.setattr(demo_app, "_predict", lambda text: "claramente negativo")
    assert demo_app.classify_text("la acción se desploma") == "negativo"


def test_classify_text_reports_invalid(monkeypatch):
    monkeypatch.setattr(demo_app, "_predict", lambda text: "ni idea")
    assert demo_app.classify_text("texto raro") == "no clasificable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_demo_app.py -v`
Expected: FAIL — `demo/app.py` does not exist.

- [ ] **Step 3: Write the demo app and assets**

`demo/app.py`:
```python
"""Gradio demo for Centinela-4B financial sentiment (loads the published GGUF on CPU)."""

import os

from nebula.labels import LABELS, SYSTEM_PROMPT_ES
from nebula.validation import constrain_label

_MODEL_REPO = os.environ.get("CENTINELA_GGUF_REPO", "astromesh/Centinela-Qwen3-4B")
_GGUF_FILE = os.environ.get("CENTINELA_GGUF_FILE", "gguf/centinela-4b.Q4_K_M.gguf")

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from llama_cpp import Llama

        _llm = Llama.from_pretrained(repo_id=_MODEL_REPO, filename=_GGUF_FILE, n_ctx=1024)
    return _llm


def _predict(text: str) -> str:
    out = _get_llm().create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_ES},
            {"role": "user", "content": text},
        ],
        max_tokens=8,
        temperature=0.0,
    )
    return out["choices"][0]["message"]["content"]


def classify_text(text: str) -> str:
    label = constrain_label(_predict(text), LABELS)
    return label if label is not None else "no clasificable"


def build_ui():
    import gradio as gr

    examples = [
        "Las acciones de la empresa subieron 12% tras superar las expectativas de ganancias.",
        "El banco central mantuvo las tasas sin cambios, en línea con lo previsto.",
        "La compañía reportó pérdidas récord y recortará 5.000 empleos.",
    ]
    return gr.Interface(
        fn=classify_text,
        inputs=gr.Textbox(label="Texto financiero (español)"),
        outputs=gr.Label(label="Sentimiento"),
        examples=examples,
        title="Centinela-4B · Sentimiento financiero",
        description="Familia Centinela · Astromesh Nebula. Salida restringida a positivo/neutral/negativo.",
    )


if __name__ == "__main__":
    build_ui().launch()
```

`demo/requirements.txt`:
```
gradio>=4.0
llama-cpp-python>=0.2.80
huggingface_hub>=0.24
```

`demo/README.md`:
```markdown
---
title: Centinela-4B Sentimiento Financiero
emoji: 🛰️
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
license: apache-2.0
---

Demo of **Centinela-4B**, a Spanish financial sentiment classifier from the Astromesh Nebula
foundry. Loads the published GGUF on CPU. Example prompts only — do not paste real financial data.
```

- [ ] **Step 4: Write `scripts/08_deploy_space.py`**

`scripts/08_deploy_space.py`:
```python
"""Create/update the public Gradio Space for the Centinela-4B demo.

    uv run python scripts/08_deploy_space.py --repo astromesh/centinela-4b-demo
"""

import argparse
import os


def deploy_space(*, api, repo_id: str, demo_dir: str) -> None:
    api.create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk="gradio",
        private=False,
        exist_ok=True,
    )
    api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=demo_dir)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--demo-dir", default="demo")
    args = ap.parse_args()

    from huggingface_hub import HfApi

    deploy_space(
        api=HfApi(token=os.environ["HF_TOKEN"]), repo_id=args.repo, demo_dir=args.demo_dir
    )
    print(f"deployed space {args.repo}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_demo_app.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add demo/ scripts/08_deploy_space.py tests/test_demo_app.py
git commit -m "feat: add Gradio demo Space and deploy script"
```

---

## Task 15: Makefile

**Files:**
- Create: `Makefile`
- Test: `tests/test_makefile.py`

- [ ] **Step 1: Write the failing test**

`tests/test_makefile.py`:
```python
from pathlib import Path


def test_makefile_has_pipeline_targets():
    mk = Path("Makefile").read_text(encoding="utf-8")
    for target in ["dataset:", "train:", "eval:", "quantize:", "publish:", "test:"]:
        assert target in mk
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_makefile.py -v`
Expected: FAIL — `Makefile` does not exist.

- [ ] **Step 3: Write the Makefile**

`Makefile`:
```makefile
SIZE ?= 4b
DATASET ?= NickyNicky/Finance_sentiment_and_topic_classification_Translation_English_to_Spanish_v1

.PHONY: test lint dataset train eval quantize merge publish space

test:
	uv run pytest -v

lint:
	uv run ruff check nebula/ tests/ scripts/

dataset:
	uv run python scripts/01_build_dataset.py --dataset $(DATASET) --out data/centinela

train:
	hf jobs uv run --flavor a10g-large scripts/02_train.py -- \
		--config configs/train-$(SIZE).yaml --train data/centinela/train.jsonl --out export/adapter

merge:
	uv run python scripts/03_merge.py --base Qwen/Qwen3-4B --adapter export/adapter --out export/merged

quantize:
	bash scripts/04_quantize.sh export/merged export/centinela-$(SIZE).Q4_K_M.gguf

eval:
	uv run python scripts/05_evaluate.py --base Qwen/Qwen3-4B --tuned export/merged \
		--eval data/centinela/eval.jsonl --out eval/results/results.md

publish:
	uv run python scripts/06_push_to_hub.py --size $(SIZE) --tag $(TAG) \
		--dataset-hash $(DATASET_HASH) --commit $(COMMIT) --n-train $(N_TRAIN) --n-eval $(N_EVAL)

space:
	uv run python scripts/08_deploy_space.py --repo $(HF_ORG)/centinela-$(SIZE)-demo
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_makefile.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add Makefile tests/test_makefile.py
git commit -m "chore: add Makefile pipeline targets"
```

---

## Task 16: CI workflows + OSS governance

**Files:**
- Create: `.github/workflows/eval-gate.yml`
- Create: `.github/workflows/publish.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CITATION.cff`
- Create: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Write `eval-gate.yml` (unit tests + lint on PR)**

`.github/workflows/eval-gate.yml`:
```yaml
name: eval-gate
on: [pull_request, push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run ruff check nebula/ tests/ scripts/
      - run: uv run pytest -v
```

Note: the GPU-backed model eval runs as an HF Job, not in GitHub CI. This workflow enforces the
library/scoring logic (including the tier-gate logic in `05_evaluate.py`). The full model-vs-base
gate is run via `make eval` before `make publish`.

- [ ] **Step 2: Write `publish.yml` (on tag v*)**

`.github/workflows/publish.yml`:
```yaml
name: publish
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Publish to HF Hub
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
          HF_ORG: ${{ secrets.HF_ORG }}
        run: |
          echo "Artifacts (adapter/merged/gguf) must be produced via HF Jobs beforehand."
          echo "This job publishes prepared artifacts; see Makefile 'publish' target."
```

- [ ] **Step 3: Write governance files**

`LICENSE`: the standard Apache-2.0 license text (fetch from https://www.apache.org/licenses/LICENSE-2.0.txt).

`NOTICE`:
```
Astromesh Nebula — Centinela model family
Copyright 2026 Astromesh

This product fine-tunes Qwen3 (Qwen/Qwen3-4B), © Alibaba Cloud, licensed under Apache-2.0.
Training data derived from NickyNicky/Finance_sentiment_and_topic_classification_
Translation_English_to_Spanish_v1 (Apache-2.0).
```

`CONTRIBUTING.md`:
```markdown
# Contributing to Astromesh Nebula

1. Fork and branch from `develop`.
2. `uv sync --extra dev`, then `uv run pytest -v` and `uv run ruff check`.
3. Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
4. A model change must not regress the eval tier threshold (`configs/eval.yaml`).
```

`CODE_OF_CONDUCT.md`:
```markdown
# Code of Conduct

This project follows the Contributor Covenant v2.1. Report issues to conduct@astromesh.dev.
```

`SECURITY.md`:
```markdown
# Security Policy

Report vulnerabilities privately to security@astromesh.dev. Do not open public issues for
security reports. Model outputs are not financial or legal advice and must be validated.
```

`CITATION.cff`:
```yaml
cff-version: 1.2.0
title: "Centinela-4B (Astromesh Nebula)"
message: "If you use this model, please cite it."
authors:
  - name: "Astromesh"
version: "0.1.0"
license: Apache-2.0
```

`.github/PULL_REQUEST_TEMPLATE.md`:
```markdown
## What
## Why
## Tests
- [ ] `uv run pytest -v` passes
- [ ] `uv run ruff check` clean
- [ ] No eval-tier regression (if model-affecting)
```

`.github/ISSUE_TEMPLATE/bug_report.md`:
```markdown
---
name: Bug report
about: Report a problem
---

**What happened**
**Expected**
**Repro steps**
**Environment**
```

- [ ] **Step 4: Write `README.md` and `CLAUDE.md`**

`README.md`:
```markdown
# Astromesh Nebula

Open-model foundry of the Astromesh ecosystem — *where models are born*. First family:
**Centinela**, Spanish-first models for finance & back-office work in LATAM.

## Centinela-4B (v0.1)
A Spanish financial **sentiment** classifier (`positivo` / `neutral` / `negativo`), QLoRA
fine-tuned from `Qwen/Qwen3-4B`, released under Apache-2.0 with a deterministic output-validation
layer. Runs cheap, self-hosted, even on CPU via GGUF.

## Pipeline
`make dataset` → `make train` (HF Jobs) → `make merge` → `make quantize` → `make eval` →
`make publish`. See `docs` and the per-script docstrings.

## Quickstart (consumers)
```bash
ollama run hf.co/astromesh/Centinela-Qwen3-4B:Q4_K_M
```
```

`CLAUDE.md`:
```markdown
# CLAUDE.md — Astromesh Nebula

Open-model foundry. Pure logic lives in `nebula/` (unit-tested); thin CLIs in `scripts/01..08`.
GPU work (train/merge/quantize) runs on HF Jobs. Python 3.12+/3.11+, `uv`, `ruff` (line 100),
`pytest`. Conventional commits. First family: Centinela (Spanish financial sentiment).

Build/test: `uv sync --extra dev` · `uv run pytest -v` · `uv run ruff check nebula/ tests/ scripts/`
```

- [ ] **Step 5: Verify tests still pass**

Run: `uv run pytest -v`
Expected: full suite passes.

- [ ] **Step 6: Commit**

```bash
git add .github/ LICENSE NOTICE CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md CITATION.cff README.md CLAUDE.md
git commit -m "chore: add CI workflows and OSS governance files"
```

---

## Task 17: End-to-end dry run and final verification

**Files:** none (verification only)

- [ ] **Step 1: Full unit suite + lint**

Run:
```bash
uv run pytest -v
uv run ruff check nebula/ tests/ scripts/
```
Expected: all tests pass; lint clean.

- [ ] **Step 2: Build the real dataset (network)**

Run:
```bash
uv sync --extra eval
make dataset
```
Expected: `data/centinela/{train,eval}.jsonl` + `labels.json` created; printed stats show
balanced `label_counts` across the three classes and a non-trivial `n_train`/`n_eval`.

- [ ] **Step 3: (Cloud) train → merge → quantize → eval**

Run, in order (requires `HF_TOKEN`, org access, GPU job flavor):
```bash
make train          # HF Jobs QLoRA -> export/adapter
make merge          # -> export/merged
make quantize       # -> export/centinela-4b.Q4_K_M.gguf
make eval           # writes eval/results/results.md, exits non-zero if gate fails
```
Expected: `make eval` prints the comparison table and `GATE: PASS` (macro-F1 ≥ 0.85 and >
base). If it fails, tune `configs/train-4b.yaml` (epochs/lr) and retrain — do not publish.

- [ ] **Step 4: (Cloud) publish model, dataset, and Space**

Run (only after the gate passes, and the `astromesh` HF org + write token exist):
```bash
export HF_ORG=astromesh
make publish TAG=v0.1 DATASET_HASH=<from step 2> COMMIT=$(git rev-parse --short HEAD) \
  N_TRAIN=<n_train> N_EVAL=<n_eval>
uv run python scripts/07_publish_dataset.py --repo $HF_ORG/centinela-sentiment-es
make space
```
Expected: public model repo `astromesh/Centinela-Qwen3-4B` (with README card + GGUF + adapter,
tag `v0.1`), dataset repo, and a working demo Space.

- [ ] **Step 5: Verify the published model loads (consumer smoke)**

Run:
```bash
ollama run hf.co/astromesh/Centinela-Qwen3-4B:Q4_K_M "Clasificá: La empresa duplicó sus ganancias este trimestre."
```
Expected: responds with `positivo` (or a string the validation layer maps to it).

- [ ] **Step 6: Final commit (results report)**

```bash
git add eval/results/results.md
git commit -m "docs: add Centinela-4B v0.1 evaluation results"
```

---

## Self-review notes (coverage vs spec)

- **§2 goals** (real public model end-to-end): Tasks 9–17. ✅
- **§3 decisions** (HF Jobs, vertical 4B, sentiment task, frontier off): Tasks 8, 10, 11. ✅
- **§4 layout** (nebula lib, scripts 01–08, eval, demo, model_card, governance, CI): Tasks 1–16. ✅
- **§5 eval contract** (eval-first, macro-F1 ≥ 0.85, must-beat-base, validation layer): Tasks 3, 4, 6, 8, 10. ✅
- **§5 deterministic validation**: Task 3 (`constrain_label`), used in Tasks 6, 10, 14. ✅
- **§6 pipeline** (10 stages): Tasks 9–14 + Makefile (15) + dry run (17). ✅
- **§7 risks** (invalid labels, leakage, cost, token-not-yet, threshold, license, version pin):
  Tasks 3, 5, 9 (dedup), 11 (cost note), 16 (NOTICE), modelcard reproducibility (Task 7). ✅
- **§8 testing** (scorer self-test, dataset build, validation, eval-gate, Space smoke):
  Tasks 4, 9, 3, 16, 14. ✅
- **Deferred** (8B, router, serving, k3s, AWQ): not in any task — correct. ✅
```
