---
title: Installation
description: Install Astromesh using your preferred method
---

Astromesh can be installed from source for development, pulled as a Docker image for containerized deployments, or installed via APT on Debian/Ubuntu systems for production use with systemd.

## Prerequisites

| Requirement | Version | Notes |
|------------|---------|-------|
| **Python** | 3.12+ | Required for source installs |
| **uv** | Latest | Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/)) |
| **Git** | Any recent | To clone the repository |
| **Docker** | 24+ | Optional, for containerized deployment |
| **Rust toolchain** | 1.75+ | Optional, for native extensions (5-50x speedup on CPU-bound paths) |

## From Source (Development)

This is the recommended method for development, experimentation, and contributing to Astromesh.

### 1. Clone the repository

```bash
git clone https://github.com/monaccode/astromesh.git
cd astromesh
```

### 2. Install dependencies

Install the base package:

```bash
uv sync
```

Or install with specific optional extras depending on your needs:

```bash
uv sync --extra all    # Everything — recommended for getting started
```

The following optional extras are available:

| Extra | What It Adds |
|-------|-------------|
| `redis` | Redis memory backend (conversational memory, caching) |
| `postgres` | PostgreSQL backend (episodic memory, pgvector) |
| `sqlite` | SQLite backend (lightweight local memory) |
| `chromadb` | ChromaDB vector store for semantic memory |
| `qdrant` | Qdrant vector store for semantic memory |
| `faiss` | FAISS vector store for local semantic memory |
| `embeddings` | Sentence-transformers for local embedding generation |
| `onnx` | ONNX Runtime provider for model inference |
| `ml` | ML training and fine-tuning utilities |
| `observability` | OpenTelemetry SDK, Prometheus exporter |
| `mcp` | Model Context Protocol client and server support |
| `all` | All of the above |

You can combine extras as needed:

```bash
uv sync --extra redis --extra postgres --extra mcp
```

### 3. Verify the installation

Run the test suite to confirm everything is working:

```bash
uv run pytest -v
```

Expected output:

```
==================== test session starts ====================
platform linux -- Python 3.12.x, pytest-8.x.x, pluggy-1.x.x
configfile: pyproject.toml
plugins: respx-0.x.x, anyio-4.x.x, asyncio-0.x.x
asyncio: mode=auto
collected XX items

tests/test_api.py::test_health PASSED
tests/test_api.py::test_run_agent PASSED
tests/test_runtime.py::test_bootstrap PASSED
...
==================== XX passed in X.XXs ====================
```

### 4. (Optional) Build Rust native extensions

For 5-50x speedup on CPU-bound code paths:

```bash
pip install maturin
maturin develop --release
```

Verify the extensions loaded:

```bash
uv run python -c "from astromesh._native import fast_router; print('Native extensions loaded')"
```

```
Native extensions loaded
```

Without the Rust extensions, Astromesh falls back to pure Python automatically. You can also force the Python fallback at runtime by setting `ASTROMESH_FORCE_PYTHON=1`.

## Docker Image

Pull the official Astromesh image:

```bash
docker pull monaccode/astromesh:latest
```

Run with environment-based configuration:

```bash
docker run -d \
  --name astromesh \
  -p 8000:8000 \
  -e ASTROMESH_LOG_LEVEL=info \
  -e OLLAMA_ENDPOINT=http://host.docker.internal:11434 \
  -v ./config:/etc/astromesh \
  monaccode/astromesh:latest
```

Verify the container is running:

```bash
curl http://localhost:8000/v1/health
```

```json
{
  "status": "healthy",
  "version": "0.10.0",
  "agents_loaded": 3,
  "uptime_seconds": 12.4
}
```

For full Docker deployment guides including Docker Compose with Ollama, PostgreSQL, Redis, and the observability stack, see the [Docker Single Node](/astromesh/deployment/docker-single/) deployment guide.

## Debian Package (Linux)

For Debian and Ubuntu systems, Astromesh is available as a `.deb` package that installs the daemon, CLI, and systemd service.

### 1. Download package from GitHub Releases

```bash
curl -LO https://github.com/monaccode/astromesh/releases/latest/download/astromesh_<VERSION>_amd64.deb
```

### 2. Install

```bash
sudo apt install ./astromesh_<VERSION>_amd64.deb
```

### 3. Verify the installation

```bash
astromeshctl status
```

Expected output:

```
Astromesh Runtime Status
========================
Daemon:     active (running)
PID:        1842
Uptime:     0h 2m 14s
Config:     /etc/astromesh/
Agents:     3 loaded, 3 healthy
API:        http://127.0.0.1:8000
```

The package installs:

| Component | Location |
|-----------|----------|
| Daemon binary | `/usr/bin/astromeshd` |
| CLI binary | `/usr/bin/astromeshctl` |
| Configuration | `/etc/astromesh/` |
| State data | `/var/lib/astromesh/` |
| Logs | `/var/log/astromesh/` |
| systemd unit | `/etc/systemd/system/astromeshd.service` |

For detailed production configuration with systemd, see the [Astromesh OS](/astromesh/deployment/astromesh-os/) guide.

> Note: A public APT repository URL is not available yet. Until then, install from GitHub Releases.

## Verify Installation

Regardless of your installation method, you can verify that Astromesh is running with a health check:

```bash
curl http://localhost:8000/v1/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.10.0",
  "agents_loaded": 3,
  "uptime_seconds": 42.7
}
```

A `"status": "healthy"` response confirms the runtime has started, loaded its configuration, and is ready to serve agent requests.

## Next Steps

With Astromesh installed, head to the [Quick Start](/astromesh/getting-started/quickstart/) guide to run your first agent in under 5 minutes.
