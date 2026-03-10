---
title: "Standalone (from source)"
description: "Run Astromesh from source for development"
---

This guide walks you through running Astromesh directly from the source repository. This is the fastest way to get started for development, experimentation, and CI pipelines.

## What and Why

Running from source gives you direct access to the codebase, hot-reload on changes, and the full test suite. There is no Docker, no systemd, no packaging layer between you and the runtime. This is the right choice when you are:

- Developing Astromesh itself or writing custom providers/tools
- Experimenting with agent configurations before deploying
- Running agents in a CI pipeline
- Learning how the runtime works

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Python | 3.12+ | `python3 --version` |
| uv | latest | `uv --version` |
| Git | any | `git --version` |
| Ollama (optional) | latest | `ollama --version` |

Install `uv` if you do not have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Expected output:

```
Downloading uv...
Installing to /home/user/.local/bin
uv installed successfully.
```

## Step-by-step Setup

### 1. Clone the repository

```bash
git clone https://github.com/monaccode/astromesh.git
cd astromesh
```

Expected output:

```
Cloning into 'astromesh'...
remote: Enumerating objects: 1234, done.
remote: Counting objects: 100% (1234/1234), done.
Receiving objects: 100% (1234/1234), 256.00 KiB | 2.56 MiB/s, done.
```

### 2. Install dependencies

Base install (API server + core runtime):

```bash
uv sync
```

Expected output:

```
Resolved 42 packages in 1.2s
Prepared 42 packages in 3.4s
Installed 42 packages in 0.8s
```

For production use or to enable all backends, install with extras:

```bash
uv sync --extra all
```

#### Available extras

| Extra | What it adds | When you need it |
|-------|-------------|-----------------|
| `redis` | Redis memory backend (hiredis) | Conversational memory with Redis |
| `postgres` | AsyncPG driver | PostgreSQL episodic memory, pgvector |
| `sqlite` | aiosqlite driver | Lightweight local memory |
| `chromadb` | ChromaDB client | ChromaDB vector store |
| `qdrant` | Qdrant client | Qdrant vector store |
| `faiss` | FAISS CPU | Local FAISS vector search |
| `embeddings` | sentence-transformers | Local embedding models |
| `onnx` | ONNX Runtime | ONNX model inference |
| `ml` | PyTorch | GPU/CPU ML workloads |
| `observability` | OpenTelemetry + Prometheus | Tracing and metrics |
| `mcp` | Model Context Protocol | MCP tool servers |
| `cli` | Typer + Rich | `astromeshctl` CLI |
| `daemon` | sdnotify | `astromeshd` systemd integration |
| `mesh` | psutil | Multi-node mesh support |
| `all` | Everything above | Full installation |

You can combine extras:

```bash
uv sync --extra redis --extra postgres --extra observability
```

### 3. Configure a provider

Astromesh needs at least one LLM provider. The two easiest options are Ollama (local) or an OpenAI API key.

**Option A: Ollama (local, no API key needed)**

Install and start Ollama, then pull a model:

```bash
ollama serve &
ollama pull llama3.1:8b
```

Expected output:

```
pulling manifest...
pulling 8eeb52dfb3bb... 100% |████████████████████| 4.7 GB
verifying sha256 digest
writing manifest
success
```

The default provider configuration in `config/providers.yaml` already points to `http://localhost:11434`.

**Option B: OpenAI API key**

Set your API key as an environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

Edit `config/providers.yaml` to enable the OpenAI provider, or run the init wizard (next step).

### 4. Run the init wizard (optional)

The init wizard generates configuration files interactively:

```bash
uv run astromeshctl init
```

Expected output:

```
🔧 Astromesh Init Wizard

? Select provider: Ollama (local)
? Ollama endpoint: http://localhost:11434
? Select model: llama3.1:8b
? Enable memory? Yes
? Memory backend: SQLite (local)

✅ Configuration written to config/
   - config/runtime.yaml
   - config/providers.yaml
   - config/agents/default.agent.yaml
```

### 5. Start the server

**Option A: uvicorn directly (recommended for development)**

```bash
uv run uvicorn astromesh.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

The `--reload` flag watches for file changes and restarts automatically.

**Option B: astromeshd daemon (for testing daemon behavior)**

```bash
uv run astromeshd --config ./config/ --port 8000
```

Expected output:

```
INFO     astromeshd starting (dev mode)
INFO     Loading config from ./config/
INFO     Loaded 1 agent(s): default
INFO     Providers: ollama (healthy)
INFO     API server listening on 0.0.0.0:8000
INFO     Ready.
```

## Verification

### Health check

```bash
curl http://localhost:8000/health
```

Expected output:

```json
{
  "status": "healthy",
  "version": "0.10.0"
}
```

### List loaded agents

```bash
curl http://localhost:8000/v1/agents
```

Expected output:

```json
{
  "agents": [
    {
      "name": "default",
      "description": "Default assistant agent",
      "model": "ollama/llama3.1:8b",
      "pattern": "react"
    }
  ]
}
```

### Run an agent

```bash
curl -X POST http://localhost:8000/v1/agents/default/run \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the capital of France?"}'
```

Expected output:

```json
{
  "response": "The capital of France is Paris.",
  "agent": "default",
  "model": "ollama/llama3.1:8b",
  "tokens": {
    "prompt": 24,
    "completion": 8,
    "total": 32
  }
}
```

## Configuration

### Project structure

```
config/
├── runtime.yaml          # Server settings (host, port, defaults)
├── providers.yaml        # LLM provider connections
├── channels.yaml         # Channel adapters (WhatsApp, etc.)
└── agents/
    └── *.agent.yaml      # Agent definitions
```

### Environment variables

Secrets are passed via environment variables referenced in YAML config:

```bash
export OPENAI_API_KEY="sk-..."
export WHATSAPP_TOKEN="EAAx..."
export DATABASE_URL="postgresql://user:pass@localhost/astromesh"
```

## Common Operations

### Development workflow with hot-reload

Start the server with `--reload` so changes take effect immediately:

```bash
uv run uvicorn astromesh.api.main:app --reload
```

Edit any Python file or YAML config, and uvicorn restarts automatically.

### Running tests

```bash
# All tests
uv run pytest -v

# Single file
uv run pytest tests/test_api.py

# Single test
uv run pytest tests/test_api.py -k "test_health"

# With coverage
uv run pytest --cov=astromesh
```

Expected output (all tests):

```
========================= test session starts ==========================
collected 47 items

tests/test_api.py::test_health PASSED
tests/test_api.py::test_list_agents PASSED
tests/test_api.py::test_run_agent PASSED
...
========================= 47 passed in 3.21s ===========================
```

### Linting and formatting

```bash
# Check for lint errors
uv run ruff check astromesh/ tests/

# Auto-format code
uv run ruff format astromesh/ tests/
```

### Building Rust native extensions (optional)

Rust extensions provide 5-50x speedup for CPU-bound paths. They are optional; Python fallback is used automatically without them.

```bash
pip install maturin
maturin develop --release
```

To verify Rust extensions are loaded:

```bash
python -c "import astromesh._native; print('Rust extensions loaded')"
```

To force Python-only mode:

```bash
export ASTROMESH_FORCE_PYTHON=1
```

## Troubleshooting

### Port 8000 already in use

```
ERROR:    [Errno 98] Address already in use
```

Find and stop the process using port 8000:

```bash
lsof -i :8000
kill <PID>
```

Or start on a different port:

```bash
uv run uvicorn astromesh.api.main:app --port 8001
```

### Ollama not running

```
ConnectionError: Cannot connect to http://localhost:11434
```

Start Ollama:

```bash
ollama serve
```

Check it is running:

```bash
curl http://localhost:11434/api/tags
```

Expected output:

```json
{
  "models": [
    {"name": "llama3.1:8b", "size": 4661224960}
  ]
}
```

### Wrong Python version

```
ERROR: This project requires Python >=3.12 but the running Python is 3.11.x
```

Install Python 3.12+ and ensure `uv` uses it:

```bash
uv python install 3.12
uv sync
```

### Import errors after install

```
ModuleNotFoundError: No module named 'redis'
```

You are missing an optional dependency. Install the extra you need:

```bash
uv sync --extra redis
```

Or install everything:

```bash
uv sync --extra all
```

### Config file not found

```
FileNotFoundError: config/runtime.yaml not found
```

Make sure you are running from the repository root directory. The dev mode server looks for config in `./config/` relative to the current working directory. Run the init wizard to generate default config:

```bash
uv run astromeshctl init
```
