# Astromesh
### Agent Runtime Platform for building AI agents

<p align="center">
  <img src="assets/astromesh-logo.png" alt="Astromesh Logo" width="900" />
</p>

<p align="center">
  <a href="https://github.com/monaccode/astromesh/actions/workflows/ci.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release.yml/badge.svg" alt="Release"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-pypi.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-pypi.yml/badge.svg" alt="PyPI Publish"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-adk.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-adk.yml/badge.svg" alt="ADK Publish"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/docs.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/docs.yml/badge.svg?branch=develop" alt="Docs"></a>
  <a href="https://github.com/monaccode/astromesh/releases/latest"><img src="https://img.shields.io/github/v/release/monaccode/astromesh?include_prereleases&label=version" alt="Version"></a>
  <a href="https://pypi.org/project/astromesh/"><img src="https://img.shields.io/pypi/v/astromesh?label=Astromesh%20PyPI" alt="Astromesh PyPI"></a>
  <a href="https://test.pypi.org/project/astromesh/"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Ftest.pypi.org%2Fpypi%2Fastromesh%2Fjson&query=%24.info.version&label=Astromesh%20TestPyPI" alt="Astromesh TestPyPI"></a>
  <a href="https://pypi.org/project/astromesh-adk/"><img src="https://img.shields.io/pypi/v/astromesh-adk?label=ADK%20PyPI" alt="ADK PyPI"></a>
  <a href="https://test.pypi.org/project/astromesh-adk/"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Ftest.pypi.org%2Fpypi%2Fastromesh-adk%2Fjson&query=%24.info.version&label=ADK%20TestPyPI" alt="ADK TestPyPI"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-orbit.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-orbit.yml/badge.svg" alt="Orbit Publish"></a>
  <a href="https://pypi.org/project/astromesh-orbit/"><img src="https://img.shields.io/pypi/v/astromesh-orbit?label=Orbit%20PyPI" alt="Orbit PyPI"></a>
  <a href="https://test.pypi.org/project/astromesh-orbit/"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Ftest.pypi.org%2Fpypi%2Fastromesh-orbit%2Fjson&query=%24.info.version&label=Orbit%20TestPyPI" alt="Orbit TestPyPI"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-node.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-node.yml/badge.svg" alt="Node Release"></a>
  <a href="https://github.com/monaccode/astromesh/actions/workflows/release-cli.yml"><img src="https://github.com/monaccode/astromesh/actions/workflows/release-cli.yml/badge.svg" alt="CLI Release"></a>
  <a href="https://github.com/monaccode/astromesh/blob/develop/LICENSE"><img src="https://img.shields.io/github/license/monaccode/astromesh" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python 3.12+"></a>
</p>

<p align="center">
  <a href="https://monaccode.github.io/astromesh/"><strong>Documentation</strong></a> · <a href="https://monaccode.github.io/astromesh/getting-started/quickstart/">Quick Start</a> · <a href="https://github.com/monaccode/astromesh/releases">Releases</a>
</p>

---

> Build, orchestrate and run AI agents with multi-model routing, tools, memory, and RAG — all configured declaratively.

Astromesh is an open-source runtime for agentic systems, designed to standardize how AI agents execute, reason, and interact with external systems.

**Think of it as Kubernetes for AI Agents.**

> ⭐ If you find this project useful, consider starring the repository.

---

## Why Astromesh

Most AI applications repeatedly rebuild the same infrastructure:

- model orchestration
- tool execution
- memory systems
- RAG pipelines
- agent reasoning loops
- observability
- cost control

Astromesh centralizes these capabilities into a single runtime platform.

Instead of writing orchestration logic yourself, you define agents declaratively and let the runtime manage execution.

---

## Documentation

**Full documentation site: [monaccode.github.io/astromesh](https://monaccode.github.io/astromesh/)**

Includes getting started guides, architecture deep-dives, 7 deployment modes, configuration reference, and API docs.

Additional references in this repo:

- **Tech overview**: [`docs/TECH_OVERVIEW.md`](docs/TECH_OVERVIEW.md)
- **General architecture**: [`docs/GENERAL_ARCHITECTURE.md`](docs/GENERAL_ARCHITECTURE.md)
- **Kubernetes-style architecture diagrams**: [`docs/K8S_ARCHITECTURE.md`](docs/K8S_ARCHITECTURE.md)
- **Configuration guide**: [`docs/CONFIGURATION_GUIDE.md`](docs/CONFIGURATION_GUIDE.md)
- **WhatsApp integration**: [`docs/WHATSAPP_INTEGRATION.md`](docs/WHATSAPP_INTEGRATION.md)
- **Maia mesh guide**: [`docs/MAIA_GUIDE.md`](docs/MAIA_GUIDE.md)
- **Developer quick start**: [`docs/DEV_QUICKSTART.md`](docs/DEV_QUICKSTART.md)
- **ADK quick start**: [`docs/ADK_QUICKSTART.md`](docs/ADK_QUICKSTART.md)
- **ADK implementation status and pending work**: [`docs/ADK_PENDING.md`](docs/ADK_PENDING.md)
- **Cloud overview**: [`docs/CLOUD_OVERVIEW.md`](docs/CLOUD_OVERVIEW.md)
- **Cloud quick start**: [`docs/CLOUD_QUICKSTART.md`](docs/CLOUD_QUICKSTART.md)
- **Cloud API reference**: [`docs/CLOUD_API_REFERENCE.md`](docs/CLOUD_API_REFERENCE.md)
- **Installation (APT)**: [`docs/INSTALLATION.md`](docs/INSTALLATION.md)
- **Developer tools**: [`docs/DEVELOPER_TOOLS.md`](docs/DEVELOPER_TOOLS.md)
- **Orbit overview**: [`docs/ORBIT_OVERVIEW.md`](docs/ORBIT_OVERVIEW.md)
- **Orbit quick start**: [`docs/ORBIT_QUICKSTART.md`](docs/ORBIT_QUICKSTART.md)
- **Orbit configuration**: [`docs/ORBIT_CONFIGURATION.md`](docs/ORBIT_CONFIGURATION.md)

---

## Key Features

### Multi-Model Runtime

Run agents across multiple LLM providers:

- Ollama
- OpenAI-compatible APIs
- vLLM
- llama.cpp
- HuggingFace TGI
- ONNX Runtime

The built-in **Model Router** automatically selects the best model using strategies such as:

- cost optimized
- latency optimized
- quality first
- round robin
- capability match

---

### Multiple Agent Reasoning Patterns

Astromesh includes several orchestration strategies:

| Pattern | Description |
|---|---|
| ReAct | reasoning + tool usage loop |
| Plan & Execute | generate plan then execute |
| Pipeline | sequential processing |
| Parallel Fan-Out | multi-model collaboration |
| Supervisor | hierarchical agents |
| Swarm | distributed agent collaboration |

---

### Built-in Memory System

Agents can maintain multiple memory layers:

| Memory Type | Purpose |
|---|---|
| Conversational | chat history |
| Semantic | vector embeddings |
| Episodic | event logs |

Supported backends:

- Redis
- PostgreSQL
- SQLite
- pgvector
- ChromaDB
- Qdrant
- FAISS

---

### Retrieval-Augmented Generation (RAG)

Astromesh includes a complete RAG pipeline:

- document chunking
- embeddings
- vector search
- reranking
- context injection

Supported vector stores:

- pgvector
- ChromaDB
- Qdrant
- FAISS

---

### Tool System

Agents interact with external systems using tools:

| Type | Description |
|------|-------------|
| **Built-in** (18 tools) | web_search, http_request, sql_query, send_email, read_file, and more |
| **MCP Servers** (3) | code_interpreter, shell_exec, generate_image |
| **Agent tools** | Invoke other agents as tools for multi-agent composition |
| **Webhooks** | Call external HTTP endpoints |
| **RAG** | Query and ingest documents |

Tools are configured declaratively in agent YAML with zero-code setup for built-ins.

---

### Messaging Channels

Astromesh supports external messaging integrations.

**Current integration:**
- WhatsApp (Meta Cloud API)

**Future integrations:**
- Slack
- Telegram
- Discord
- Web chat
- Voice assistants

---

### Observability

Full observability stack with zero configuration:

- **Structured tracing** — span trees for every agent execution
- **Metrics** — counters and histograms (runs, tokens, cost, latency)
- **Built-in dashboard** — web UI at `/v1/dashboard/`
- **CLI access** — `astromeshctl traces`, `astromeshctl metrics`, `astromeshctl cost`
- **OpenTelemetry export** — compatible with Jaeger, Grafana Tempo, etc.
- **VS Code integration** — traces panel and metrics dashboard in your editor

---

### Developer Experience

Astromesh provides a complete developer toolkit:

| Tool | Description |
|------|-------------|
| **CLI** (`astromeshctl`) | Scaffold agents, run workflows, inspect traces, view metrics, validate configs |
| **Copilot** | Built-in AI assistant that helps build and debug agents |
| **VS Code Extension** | YAML IntelliSense, workflow visualizer, traces panel, metrics dashboard, copilot chat |
| **Built-in Dashboard** | Web UI at `/v1/dashboard/` with real-time observability |

```bash
# Scaffold a new agent
astromeshctl new agent customer-support

# Run it
astromeshctl run customer-support "How do I reset my password?"

# See what happened
astromeshctl traces customer-support --last 5

# Check costs
astromeshctl cost --window 24h

# Ask the copilot for help
astromeshctl ask "Why is my agent slow?"
```

---

## Architecture

Astromesh follows a layered architecture (see also [`docs/GENERAL_ARCHITECTURE.md`](docs/GENERAL_ARCHITECTURE.md) for the full reference):

```
API Layer
REST / WebSocket
        ↓
Runtime Engine
Agent lifecycle and execution
        ↓
Core Services
Model Router · Memory Manager · Tool Registry · Guardrails
        ↓
Infrastructure
LLM Providers · Vector Databases · Observability · Storage Backends
```

---

## Quick Start

### Requirements

- Python 3.12+
- uv package manager

### Install uv

```bash
pip install uv
```

### Clone the repository

```bash
git clone https://github.com/monaccode/astromesh.git
cd astromesh
```

### Install dependencies

```bash
uv sync
```

### Run the runtime

```bash
uv run uvicorn astromesh.api.main:app --reload
```

API will be available at `http://localhost:8000`

---

## Create Your First Agent

Create the file: `config/agents/my-agent.agent.yaml`

```yaml
apiVersion: astromesh/v1
kind: Agent

metadata:
  name: my-agent

spec:
  identity:
    display_name: "My Agent"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"

  prompts:
    system: |
      You are a helpful assistant.

  orchestration:
    pattern: react
```

### Run the Agent

```bash
curl -X POST http://localhost:8000/v1/agents/my-agent/run \
  -H "Content-Type: application/json" \
  -d '{"query":"Hello","session_id":"demo"}'
```

---

## Example Use Cases

### AI Copilots
- developer assistants
- support agents
- internal knowledge assistants

### Autonomous Workflows
- document processing
- business automation
- API orchestration

### Multi-Agent Systems
- distributed reasoning
- hierarchical agents
- collaborative agents

### AI APIs
Expose agents as programmable services.

---

## Docker Deployment

Astromesh includes a full development stack:

```bash
docker compose up
```

Includes:

- Agent runtime API
- Ollama inference
- vLLM inference
- embeddings service
- PostgreSQL + pgvector
- Redis
- Prometheus
- Grafana

---

## Ecosystem

Astromesh is an ecosystem of six components covering the full agent lifecycle:

| Component | Description | Package | Status |
|-----------|-------------|---------|--------|
| **Core Runtime** | Multi-model agent engine with 6 orchestration patterns | `astromesh` | v0.23.1 |
| **ADK** | Python-first agent SDK with decorators and CLI | `astromesh-adk` | v0.1.5 |
| **CLI** | CLI tool for managing nodes and clusters | `astromesh-cli` | v0.1.1 |
| **Node** | Cross-platform system installer and daemon | `astromesh-node` | v0.1.0 |
| **Forge** | Visual agent builder with wizard, canvas, and templates | `astromesh-forge` | v0.1.0 |
| **Orbit** | Cloud-native IaC deployment with Terraform | `astromesh-orbit` | v0.1.2 |
| **Cortex** | Desktop IDE for agent engineering (Electron + React) | `astromesh-cortex` | v0.3.0 |
| **Nexus** | Kubernetes control plane for multi-tenant cloud agents | `astromesh-nexus` | v0.3.0 |

---

## Astromesh ADK

The **Agent Development Kit** is a Python SDK for building, testing, and deploying agents on Astromesh. It provides a high-level API that wraps the runtime, so you can define agents in Python code instead of YAML.

```bash
pip install astromesh-adk
```

```python
from astromesh_adk import Agent, Tool

agent = Agent(
    name="my-agent",
    model="ollama/llama3.1:8b",
    system_prompt="You are a helpful assistant.",
    tools=[Tool.web_search(), Tool.http_request()],
)

response = agent.run("What's the weather in Buenos Aires?")
```

- **Python-first** — Define agents, tools, memory, and guardrails in code
- **CLI included** — `astromesh-adk init`, `astromesh-adk run`, `astromesh-adk test`
- **Hot reload** — Edit your agent code and see changes immediately
- **Compatible** — Generates standard Astromesh agent YAML under the hood

Docs: [`docs/ADK_QUICKSTART.md`](docs/ADK_QUICKSTART.md) | [`docs/ADK_PENDING.md`](docs/ADK_PENDING.md)

---

## Astromesh Node

Cross-platform system installer and daemon — deploy Astromesh as a **native system service** on Linux, macOS, and Windows.

```bash
# Debian/Ubuntu
sudo dpkg -i astromesh-node-0.1.0-amd64.deb
sudo astromeshctl init --profile full
sudo systemctl start astromeshd
```

- **Cross-platform** — `.deb` (Debian/Ubuntu), `.rpm` (RHEL/Fedora), `.tar.gz` (macOS), `.zip` (Windows)
- **System service** — systemd, launchd, or Windows Service with auto-restart
- **CLI management** — `astromeshctl` with 17 commands (status, doctor, agents, mesh, etc.)
- **7 profiles** — full, gateway, worker, inference, mesh-gateway, mesh-worker, mesh-inference

Docs: [Node Introduction](https://monaccode.github.io/astromesh/node/introduction/) | [Installation Guides](https://monaccode.github.io/astromesh/node/quick-start/)

---

## Astromesh Cloud

A managed multi-tenant platform for deploying and operating Astromesh agents as a service. Includes a REST API, a web-based Studio for no-code agent design, and usage tracking.

```bash
# Cloud API (FastAPI + PostgreSQL)
cd astromesh-cloud/api && uvicorn astromesh_cloud.main:app --port 8001

# Cloud Studio (Next.js)
cd astromesh-cloud/web && npm run dev
```

- **Multi-tenant** — Organizations, members, API keys, rate limiting
- **Agent lifecycle** — draft → deployed → paused with quota enforcement
- **BYOK** — Bring your own provider keys (OpenAI, Anthropic, etc.) with Fernet encryption
- **Studio** — 5-step agent wizard, deploy preview, test chat, usage dashboard
- **Runtime proxy** — Proxies execution to Astromesh core with namespace isolation

Docs: [`docs/CLOUD_OVERVIEW.md`](docs/CLOUD_OVERVIEW.md) | [`docs/CLOUD_QUICKSTART.md`](docs/CLOUD_QUICKSTART.md) | [`docs/CLOUD_API_REFERENCE.md`](docs/CLOUD_API_REFERENCE.md)

---

## Astromesh Orbit

Orbit is a standalone deployment tool that provisions the full Astromesh stack on cloud infrastructure with a single command. It generates Terraform from Jinja2 templates using a provider plugin architecture.

```bash
pip install astromesh-orbit[gcp]

astromeshctl orbit init --provider gcp --preset starter
astromeshctl orbit plan
astromeshctl orbit apply
```

One command deploys Cloud Run (runtime + Cloud API + Studio), Cloud SQL, Memorystore, Secret Manager, VPC networking, and IAM — all configured from a single `orbit.yaml` file.

- **GCP first** — Cloud-native managed services. AWS and Azure providers on the roadmap.
- **Escape hatch** — `orbit eject` produces standalone Terraform files with no Orbit dependency.
- **Two presets** — Starter (~$30/mo) and Pro (~$150/mo), or configure every field manually.

Docs: [`docs/ORBIT_OVERVIEW.md`](docs/ORBIT_OVERVIEW.md) | [`docs/ORBIT_QUICKSTART.md`](docs/ORBIT_QUICKSTART.md) | [`docs/ORBIT_CONFIGURATION.md`](docs/ORBIT_CONFIGURATION.md)

---

## Project Structure

```
astromesh/                      # Core runtime
 ├── api/                       #   REST + WebSocket API
 ├── runtime/                   #   Agent lifecycle engine
 ├── core/                      #   Model router, memory, tools, guardrails
 ├── providers/                 #   LLM provider adapters
 ├── orchestration/             #   ReAct, Plan&Execute, Pipeline, etc.
 ├── rag/                       #   RAG pipeline
 ├── channels/                  #   WhatsApp, Slack, etc.
 └── mesh/                      #   Distributed agent networking

astromesh-adk/                  # Agent Development Kit (pip install astromesh-adk)
 ├── astromesh_adk/
 └── tests/

astromesh-cloud/                # Managed platform (SaaS)
 ├── api/                       #   Cloud API (FastAPI + PostgreSQL)
 └── web/                       #   Cloud Studio (Next.js)

astromesh-orbit/                # Cloud deployment tool (pip install astromesh-orbit)
 ├── astromesh_orbit/
 │   ├── core/                  #   Provider Protocol + data types
 │   ├── terraform/             #   Terraform runner + state backend
 │   ├── wizard/                #   Interactive setup + presets
 │   └── providers/gcp/         #   GCP templates
 └── tests/

astromesh-cli/                  # Astromesh CLI — standalone CLI tool for managing nodes and clusters
 ├── astromesh_cli/
 └── tests/

astromesh-node/                 # Astromesh Node — daemon, CLI, and packaging (pip install astromesh-node)
 ├── daemon/                    #   astromeshd process (systemd / launchd / Windows Service)
 ├── cli/                       #   astromeshctl command-line tool
 ├── packaging/                 #   APT/RPM/Homebrew packaging configs
 └── tests/
```

Configuration:

```
config/
 ├── agents/
 ├── rag/
 ├── providers.yaml
 └── runtime.yaml

orbit.yaml                      # Orbit deployment config (project root)
```

---

## Optional: Rust Native Extensions

Astromesh includes optional Rust-powered native extensions for CPU-bound hot paths (chunking, PII redaction, token counting, routing). When compiled, they provide 5-50x speedup. Without them, the system falls back to pure Python automatically.

```bash
pip install maturin
maturin develop --release
```

See [`docs/NATIVE_ESTENSIONS_RUST.md`](docs/NATIVE_ESTENSIONS_RUST.md) for details.

---

## Roadmap

- [x] Multi-model runtime with 6 providers
- [x] 6 orchestration patterns (ReAct, Plan&Execute, Pipeline, Fan-Out, Supervisor, Swarm)
- [x] Memory system (conversational, semantic, episodic)
- [x] RAG pipeline with 4 vector stores
- [x] 18 built-in tools + 3 MCP servers
- [x] Full observability (tracing, metrics, dashboard)
- [x] CLI with copilot
- [x] Multi-agent composition (agent-as-tool)
- [x] Workflow YAML engine
- [x] VS Code extension
- [x] Agent Development Kit (ADK) — Python SDK
- [x] Astromesh Cloud — managed multi-tenant platform
- [x] Astromesh Orbit — cloud-native deployment (GCP)
- [ ] Distributed agent execution
- [ ] GPU-aware model scheduling
- [ ] Event-driven agents
- [ ] Multi-tenant runtime
- [ ] Agent marketplace

---

## Contributing

Contributions are welcome.

Ways to contribute:

- new providers
- orchestration patterns
- vector stores
- tools
- bug fixes
- documentation improvements

---

## License

Apache-2.0 (see `LICENSE`)

---

## Community

Community resources coming soon:

- Discord
- Roadmap discussions
- Contributor guide

---

> ⭐ If you like Astromesh, give the repo a star. It helps the project reach more developers.