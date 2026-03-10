# Developer Quick Start

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | `python3 --version` |
| uv | latest | [astral.sh/uv](https://astral.sh/uv) |
| Git | any | |
| Docker | optional | Required for mesh mode |

## Quick Start (Single Node)

```bash
git clone https://github.com/monaccode/astromesh.git
cd astromesh
uv sync --extra all
make dev-single
# or: astromeshctl init --dev && astromeshd --config ./config --log-level debug
```

Verify the node is running:

```bash
curl http://localhost:8000/health
```

## Docker Mesh (3 Nodes)

> **Using the pre-built image?** Skip `make dev-mesh` and use the ready-made compose recipes in [`recipes/`](../recipes/) instead — no source checkout needed. See the [Maia Developer Guide](MAIA_GUIDE.md) for details.

```bash
make dev-mesh
```

This starts a 3-node cluster (from source):

- **Gateway** (port 8000) — receives API requests, routes to workers
- **Worker** — executes agent pipelines and tool calls
- **Inference** — hosts local models (Ollama)

Nodes discover each other via the gossip protocol. All three form a mesh automatically.

Verify the mesh by running an agent:

```bash
curl http://localhost:8000/v1/agents/support-agent/run \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello"}'
```

Stop the mesh:

```bash
make dev-stop
```

## Using the Init Wizard

```bash
astromeshctl init --dev
```

The wizard walks through:

1. **Role selection** — gateway, worker, inference, or standalone
2. **Provider configuration** — API keys for OpenAI/Anthropic/etc., or local Ollama endpoint
3. **Config generation** — writes YAML files to `./config/`

For CI pipelines, skip the prompts:

```bash
astromeshctl init --dev --non-interactive
```

## Your First Agent

Create a file at `config/agents/hello.agent.yaml`:

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: hello-agent
spec:
  identity:
    description: A minimal test agent
  model:
    primary:
      provider: openai
      model: gpt-4o-mini
  prompts:
    system: |
      You are a helpful assistant. Keep responses brief.
  orchestration:
    pattern: react
    max_iterations: 3
    timeout: 30
```

Call it:

```bash
curl http://localhost:8000/v1/agents/hello-agent/run \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "What is 2+2?"}'
```

See `config/agents/support-agent.agent.yaml` for a full example with tools, memory, and guardrails.

## Makefile Reference

| Target | Description |
|--------|-------------|
| `make help` | Show all targets |
| `make dev-single` | Run single node from source |
| `make dev-mesh` | Start 3-node Docker mesh |
| `make dev-stop` | Stop Docker mesh |
| `make dev-logs` | Tail mesh logs |
| `make test` | Run tests |
| `make test-cov` | Tests with coverage |
| `make lint` | Lint with ruff |
| `make fmt` | Format with ruff |
| `make build-deb` | Build .deb package |
| `make build-rust` | Build Rust native extensions |

## One-Liner Install (Linux)

For deploying on servers:

```bash
curl -fsSL https://monaccode.github.io/astromesh/get-astromesh.sh | bash
```

This installs the `astromeshd` daemon and `astromeshctl` CLI, then runs `astromeshctl init` to configure the node.

## Rust Extensions (Optional)

Native Rust extensions provide 5-50x speedup on CPU-bound paths (embedding ops, message parsing).

```bash
make build-rust
```

Requires `maturin` and a Rust toolchain. Without them, pure-Python fallbacks are used automatically. Set `ASTROMESH_FORCE_PYTHON=1` to disable native extensions at runtime.

## Troubleshooting

**Port 8000 already in use**

```bash
# Find what's using the port
lsof -i :8000
# Or pick a different port
astromeshd --config ./config --port 8001
```

**Ollama not running**

The inference node expects Ollama at `http://localhost:11434`. Start it:

```bash
ollama serve
```

Or point to a remote instance via `OLLAMA_HOST` in your environment.

**Python version mismatch**

Astromesh requires Python 3.12+. Check your version:

```bash
python3 --version
```

If you have multiple versions installed, point uv at the right one:

```bash
uv python pin 3.12
uv sync --extra all
```

**Docker mesh nodes failing to connect**

Ensure Docker networking is healthy:

```bash
docker network ls
make dev-stop && make dev-mesh
```

**Tests failing with import errors**

Reinstall dependencies:

```bash
uv sync --extra all
uv run pytest -v
```
