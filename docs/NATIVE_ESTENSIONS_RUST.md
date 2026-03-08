# Rust Native Extensions

Astromesh includes optional Rust native extensions (`astromesh._native`) for CPU-bound hot paths. When compiled, they provide 5-50x speedup for chunking, PII redaction, token counting, and more. When not compiled, the system falls back to pure Python automatically.

## Architecture

```
astromesh._native (PyO3 cdylib)
├── chunking     — Fixed, Recursive, Sentence chunkers + cosine similarity
├── guardrails   — PII redaction (pre-compiled regex) + topic filter (Aho-Corasick)
├── tokens       — Token budget strategy
├── ratelimit    — Sliding-window rate limiter (VecDeque)
├── routing      — EMA update, vision detection, candidate ranking
├── cost_tracker — Indexed cost/usage queries
└── json_parser  — serde_json → Python objects
```

## Building

### Prerequisites

- Rust 1.80+ (`rustup` recommended)
- Windows: MSVC build tools + Windows SDK
- Linux/macOS: standard C toolchain
- Python 3.12+
- `maturin` (`pip install maturin`)

### Build the extension

```bash
maturin develop --release          # Build and install into current venv
```

### Verify

```bash
python -c "from astromesh._native import RustPiiRedactor; print('Native extensions loaded')"
```

## Fallback behavior

All Python modules use a standard pattern:

```python
try:
    from astromesh._native import rust_fixed_chunk as _native_chunk
except ImportError:
    _native_chunk = None
```

Set `ASTROMESH_FORCE_PYTHON=1` to disable native extensions at runtime (useful for debugging or testing).

## Components

| Component | Python module | Rust function/class | Speedup |
|---|---|---|---|
| Fixed chunking | `rag/chunking/fixed.py` | `rust_fixed_chunk` | 10-50x |
| Recursive chunking | `rag/chunking/recursive.py` | `rust_recursive_chunk` | 10-50x |
| Sentence chunking | `rag/chunking/sentence.py` | `rust_sentence_chunk` | 10-50x |
| Cosine similarity | `rag/chunking/semantic.py` | `rust_cosine_similarity` | 5-20x |
| PII redaction | `core/guardrails.py` | `RustPiiRedactor` | 5-20x |
| Topic filter | `core/guardrails.py` | `RustTopicFilter` | 5-10x |
| Token budget | `memory/strategies/token_budget.py` | `RustTokenBudget` | 10-30x |
| Rate limiter | `core/tools.py` | `RustRateLimiter` | O(log n) vs O(n) |
| EMA update | `core/model_router.py` | `rust_ema_update` | 2-5x |
| Vision detection | `core/model_router.py` | `rust_detect_vision` | 2-5x |
| Candidate ranking | `core/model_router.py` | `rust_rank_candidates` | 2-5x |
| Cost queries | `observability/cost_tracker.py` | `RustCostIndex` | O(log n) |
| JSON parsing | `orchestration/patterns.py` | `rust_json_loads` | 2-5x |

## Running benchmarks

```bash
uv run pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmark.json
```

## Testing

```bash
# Test both native and Python backends
uv run pytest tests/test_native_*.py -v

# Test Python-only fallback
ASTROMESH_FORCE_PYTHON=1 uv run pytest -v

# Test with native extensions
maturin develop --release && uv run pytest -v
```
