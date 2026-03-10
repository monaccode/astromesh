---
title: Rust Native Extensions
description: Optional 5-50x speedup for CPU-bound operations
---

Astromesh includes optional Rust native extensions that accelerate CPU-bound operations. When compiled, these extensions are loaded automatically via the `astromesh._native` module. When not available, Astromesh falls back to equivalent pure-Python implementations with zero configuration changes.

## What Gets Optimized

The Rust extensions cover seven modules that sit on hot paths in the agent execution pipeline:

| Module | Operations | Python Fallback |
|--------|-----------|-----------------|
| **chunking** | Fixed, recursive, and sentence text chunking; cosine similarity; semantic grouping | `astromesh.rag.chunking.*` |
| **guardrails** | PII detection and redaction (`RustPiiRedactor`), topic filtering (`RustTopicFilter`) | `astromesh.core.guardrails` |
| **tokens** | Token budget calculation (`RustTokenBudget`) | `astromesh.memory.strategies.token_budget` |
| **ratelimit** | Sliding-window rate limiter (`RustRateLimiter`) | `astromesh.core.tools` |
| **routing** | EMA latency updates, candidate ranking, vision detection | `astromesh.core.model_router` |
| **cost_tracker** | Cost indexing with filtered aggregation (`RustCostIndex`) | `astromesh.observability.cost_tracker` |
| **json_parser** | Fast JSON deserialization (`rust_json_loads`) | stdlib `json.loads` |

## Benchmark Comparison

The following benchmarks were measured using `pytest-benchmark` on representative workloads. Results will vary by hardware, but the relative speedups are consistent.

| Operation | Input Size | Python | Rust | Speedup |
|-----------|-----------|--------|------|---------|
| Fixed chunking | 1 KB | 0.12 ms | 0.02 ms | ~6x |
| Fixed chunking | 100 KB | 8.5 ms | 0.4 ms | ~21x |
| Fixed chunking | 1 MB | 85 ms | 3.2 ms | ~27x |
| Sentence chunking | 1 KB | 0.15 ms | 0.03 ms | ~5x |
| Sentence chunking | 100 KB | 12 ms | 0.5 ms | ~24x |
| PII redaction | 1 KB | 2.1 ms | 0.08 ms | ~26x |
| Token budget calc | 50 messages | 0.8 ms | 0.04 ms | ~20x |
| Rate limiter check | 1000 calls | 1.2 ms | 0.05 ms | ~24x |
| Candidate ranking | 10 providers | 0.3 ms | 0.01 ms | ~30x |
| Cost aggregation | 10k records | 15 ms | 0.3 ms | ~50x |
| JSON parsing | 100 KB | 2.5 ms | 0.5 ms | ~5x |

Run the benchmarks yourself:

```bash
uv run pytest tests/benchmarks/ -v --benchmark-only
```

## Prerequisites

You need a Rust toolchain and `maturin` (the Rust-to-Python build tool):

1. **Install Rust** via [rustup](https://rustup.rs/):

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source $HOME/.cargo/env
   ```

2. **Install maturin**:

   ```bash
   pip install maturin
   ```

3. **Verify**:

   ```bash
   rustc --version   # Should be 1.70+
   maturin --version
   ```

## Building the Extensions

From the repository root, build and install the native module into your current Python environment:

```bash
maturin develop --release
```

This compiles the Rust code in `native/` and installs the resulting `astromesh._native` shared library into your site-packages. The `--release` flag enables optimizations — always use it for meaningful performance gains.

To verify the Rust code compiles without installing:

```bash
cargo check
```

To run the Rust unit tests:

```bash
cargo test
```

## Verifying the Installation

After building, confirm that Python can load the native module:

```python
python -c "from astromesh._native import RustPiiRedactor; print('Native extensions loaded')"
```

If this prints `Native extensions loaded`, the extensions are active. If it raises `ImportError`, the build did not complete or the module is not on the Python path.

## How It Works

The native extensions use [PyO3](https://pyo3.rs/) to bridge Rust and Python. The architecture is straightforward:

```
native/
├── Cargo.toml           # Rust package manifest (pyo3, regex, aho-corasick, serde)
└── src/
    ├── lib.rs           # PyO3 module registration — exposes all functions and classes
    ├── chunking.rs      # Text chunking algorithms
    ├── guardrails.rs    # PII regex patterns, topic keyword matching (aho-corasick)
    ├── tokens.rs        # Token counting and budget enforcement
    ├── ratelimit.rs     # Sliding-window rate limiter
    ├── routing.rs       # EMA updates, provider ranking, vision detection
    ├── cost_tracker.rs  # Indexed cost aggregation
    └── json_parser.rs   # serde_json wrapper
```

Each Python module checks for the native implementation at import time:

```python
try:
    from astromesh._native import RustPiiRedactor
    _HAS_NATIVE = True
except ImportError:
    _HAS_NATIVE = False
```

When the native extension is available and `ASTROMESH_FORCE_PYTHON` is not set, the Rust implementation is used. Otherwise, the pure-Python fallback runs.

The Rust crate depends on:

- **pyo3** (0.22) — Python-Rust FFI via the extension-module feature
- **regex** — high-performance regular expressions for PII detection
- **aho-corasick** — multi-pattern string matching for topic filtering
- **serde / serde_json** — fast JSON serialization and deserialization

## Runtime Toggle

You can force Python fallbacks at runtime without recompiling:

```bash
export ASTROMESH_FORCE_PYTHON=1
```

This is useful for:

- **Debugging**: stepping through Python code is easier than Rust
- **Testing**: verifying that Python and Rust implementations produce identical results
- **Profiling**: isolating whether a performance issue is in native code or elsewhere

Unset the variable (or set it to empty) to re-enable native extensions:

```bash
unset ASTROMESH_FORCE_PYTHON
```

## Automatic Fallback

If the `_native` module is not compiled, Astromesh works identically using pure-Python implementations. No configuration changes are needed. The only difference is performance on CPU-bound operations.

This means:

- Development environments do not need Rust installed
- CI pipelines can skip the native build if only testing business logic
- Deployment images can omit Rust for smaller image sizes at the cost of throughput

## CI Integration

To include native extensions in your CI pipeline, add a maturin build step before running tests:

```yaml
# GitHub Actions example
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: dtolnay/rust-toolchain@stable

      - name: Install dependencies
        run: |
          pip install uv maturin
          uv sync --extra all

      - name: Build native extensions
        run: maturin develop --release

      - name: Run tests (with native)
        run: uv run pytest -v

      - name: Run tests (Python fallback)
        env:
          ASTROMESH_FORCE_PYTHON: "1"
        run: uv run pytest -v
```

Running tests both with and without native extensions ensures the fallback paths remain correct.

## Docker

The default Astromesh Docker image (`monaccode/astromesh:latest`) does **not** include Rust extensions. This keeps the image small and the build fast.

If you need native extensions in Docker, add a Rust build stage to your Dockerfile:

```dockerfile
# Stage 1: Build native extensions
FROM rust:1.80-slim AS rust-builder
WORKDIR /app
COPY native/ native/
COPY pyproject.toml .
RUN pip install maturin && maturin build --release -o /wheels

# Stage 2: Python application
FROM python:3.12-slim
WORKDIR /app
COPY --from=rust-builder /wheels/*.whl /tmp/
RUN pip install /tmp/*.whl
COPY . .
RUN pip install uv && uv sync --extra all
CMD ["uv", "run", "uvicorn", "astromesh.api.main:app", "--host", "0.0.0.0"]
```

This multi-stage build keeps the final image free of the Rust toolchain while including the compiled extensions.
