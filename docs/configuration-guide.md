# Astromesh Configuration Guide

All Astromesh configuration files are YAML with a common header:

```yaml
apiVersion: astromesh/v1
kind: <ResourceType>
metadata:
  name: <unique-name>
```

There are 4 configuration types: **Agent**, **ProviderConfig**, **RAGPipeline**, and **RuntimeConfig**.

---

## Agent Configuration

**File location:** `config/agents/<name>.agent.yaml`
**Kind:** `Agent`

Agents are the primary resource. Each YAML file defines a fully independent agent with its model, prompts, memory, tools, and guardrails.

### Minimal Agent

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: my-agent
  version: "1.0.0"

spec:
  identity:
    display_name: "My Agent"
    description: "A simple assistant"

  model:
    primary:
      provider: ollama
      model: "llama3.1:8b"
      endpoint: "http://ollama:11434"
      parameters:
        temperature: 0.7
        max_tokens: 2048

  prompts:
    system: |
      You are a helpful assistant.

  orchestration:
    pattern: react
    max_iterations: 10
```

### Full Agent Reference

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: sales-qualifier        # Unique identifier (used in API routes)
  version: "1.0.0"
  namespace: sales              # Logical grouping
  labels:                       # Arbitrary key-value labels
    team: revenue
    tier: production

spec:
  # --- Identity ---
  identity:
    display_name: "Sales Lead Qualifier"
    description: "Qualifies incoming sales leads using BANT methodology"
    avatar: "sales-bot"         # Optional avatar identifier

  # --- Model Selection ---
  model:
    primary:
      provider: ollama          # Provider type (ollama, openai_compat, vllm, llamacpp, hf_tgi, onnx)
      model: "llama3.1:8b"      # Model name/path
      endpoint: "http://ollama:11434"
      parameters:
        temperature: 0.3        # 0.0 = deterministic, 1.0 = creative
        top_p: 0.9              # Nucleus sampling
        max_tokens: 2048        # Max response length

    fallback:                   # Optional fallback when primary fails
      provider: openai_compat
      model: "gpt-4o-mini"
      endpoint: "https://api.openai.com/v1"
      api_key_env: OPENAI_API_KEY  # Environment variable name (not the key itself)

    routing:
      strategy: cost_optimized  # cost_optimized | latency_optimized | quality_first | round_robin | capability_match
      health_check_interval: 30 # Seconds between health checks

  # --- System Prompt ---
  prompts:
    system: |
      You are a sales lead qualification assistant using BANT methodology.

      For each lead, assess:
      - **Budget**: Can they afford the solution?
      - **Authority**: Are they the decision maker?
      - **Need**: Do they have a genuine need?
      - **Timeline**: When do they plan to purchase?

      Provide a qualification score (1-10) and recommended next action.

    templates:                  # Optional named Jinja2 templates
      greeting: "Hello {{ user_name }}, how can I help you today?"

  # --- Orchestration Pattern ---
  orchestration:
    pattern: react              # react | plan_and_execute | parallel_fan_out | pipeline | supervisor | swarm
    max_iterations: 5           # Max reasoning iterations before stopping
    timeout_seconds: 60         # Optional timeout

  # --- Tools ---
  tools:
    - name: lookup_company
      type: internal            # internal | mcp | webhook | rag
      description: "Look up company information"
      parameters:
        company_name:
          type: string
          description: "Company name to look up"

  # --- Memory ---
  memory:
    conversational:
      backend: redis            # redis | postgres | sqlite
      strategy: sliding_window  # sliding_window | summary | token_budget
      max_turns: 20             # For sliding_window: how many turns to keep
      ttl: 3600                 # Optional: time-to-live in seconds (redis)

    semantic:                   # Optional: vector-based memory
      backend: chromadb         # pgvector | chromadb | qdrant | faiss
      similarity_threshold: 0.75
      max_results: 5

  # --- Guardrails ---
  guardrails:
    input:                      # Applied to user messages
      - type: pii_detection
        action: redact          # redact | block
      - type: max_length
        max_chars: 5000

    output:                     # Applied to agent responses
      - type: cost_limit
        max_tokens_per_turn: 1000
      - type: pii_detection
        action: redact
      - type: content_filter
        forbidden_keywords: ["internal", "confidential"]
      - type: topic_filter
        forbidden_topics: ["politics", "religion"]

  # --- Permissions ---
  permissions:
    allowed_actions:            # Tools this agent is allowed to use
      - lookup_company
      - search_crm
```

### Orchestration Patterns

| Pattern | Best For | Description |
|---------|----------|-------------|
| `react` | General-purpose agents | Think → Act → Observe loop. Default pattern. |
| `plan_and_execute` | Complex multi-step tasks | Creates a plan first, then executes each step. |
| `parallel_fan_out` | Multiple perspectives | Sends query to multiple models, merges results. |
| `pipeline` | Sequential processing | Chains multiple steps in order. |
| `supervisor` | Task delegation | Delegates sub-tasks to worker agents. |
| `swarm` | Multi-agent conversations | Agents hand off to each other based on context. |

### Memory Strategies

| Strategy | Description | Use When |
|----------|-------------|----------|
| `sliding_window` | Keep the last N turns | Simple conversations with bounded context |
| `summary` | Compress older turns into summaries | Long conversations that need full history |
| `token_budget` | Fit as many turns as possible within a token limit | Need precise control over context size |

### Guardrail Types

| Type | Direction | Description |
|------|-----------|-------------|
| `pii_detection` | input/output | Detects and redacts emails, phone numbers, SSNs, credit card numbers |
| `max_length` | input | Rejects messages exceeding `max_chars` |
| `cost_limit` | output | Truncates responses exceeding `max_tokens_per_turn` |
| `content_filter` | output | Blocks responses containing `forbidden_keywords` |
| `topic_filter` | output | Blocks responses matching `forbidden_topics` |

---

## Provider Configuration

**File location:** `config/providers.yaml`
**Kind:** `ProviderConfig`

Defines the available LLM providers, their endpoints, and routing behavior.

```yaml
apiVersion: astromesh/v1
kind: ProviderConfig
metadata:
  name: default-providers

spec:
  providers:
    # --- Ollama (local) ---
    ollama:
      type: ollama
      endpoint: "http://ollama:11434"
      models:
        - "llama3.1:8b"
        - "llama3.1:70b"
        - "codellama:34b"
        - "nomic-embed-text"
      health_check_interval: 30

    # --- vLLM (high-throughput) ---
    vllm:
      type: vllm
      endpoint: "http://vllm:8000"
      models:
        - "mistralai/Mistral-7B-Instruct-v0.3"
      health_check_interval: 30

    # --- OpenAI API ---
    openai:
      type: openai_compat
      endpoint: "https://api.openai.com/v1"
      api_key_env: OPENAI_API_KEY     # Name of environment variable
      models:
        - "gpt-4o"
        - "gpt-4o-mini"

    # --- HuggingFace TGI ---
    hf_tgi:
      type: hf_tgi
      endpoint: "http://embeddings:80"
      models:
        - "BAAI/bge-small-en-v1.5"

    # --- llama.cpp ---
    llamacpp:
      type: llamacpp
      endpoint: "http://llamacpp:8080"
      models:
        - "local-model"

    # --- ONNX Runtime ---
    onnx:
      type: onnx
      models:
        - "model.onnx"

  # --- Routing Settings ---
  routing:
    default_strategy: cost_optimized  # Default routing for all agents
    fallback_enabled: true            # Allow fallback to next provider on failure

    circuit_breaker:
      failure_threshold: 3            # Open circuit after N consecutive failures
      recovery_timeout: 60            # Seconds before attempting recovery
```

### Provider Types

| Type | Description | Endpoint Format |
|------|-------------|-----------------|
| `ollama` | Ollama local inference | `http://host:11434` |
| `openai_compat` | Any OpenAI-compatible API | `https://api.example.com/v1` |
| `vllm` | vLLM serving engine | `http://host:8000` |
| `llamacpp` | llama.cpp server | `http://host:8080` |
| `hf_tgi` | HuggingFace Text Generation Inference | `http://host:80` |
| `onnx` | ONNX Runtime (local) | No endpoint needed |

---

## RAG Pipeline Configuration

**File location:** `config/rag/<name>.rag.yaml`
**Kind:** `RAGPipeline`

Defines a retrieval-augmented generation pipeline for knowledge bases.

```yaml
apiVersion: astromesh/v1
kind: RAGPipeline
metadata:
  name: product-knowledge
  version: "1.0.0"

spec:
  # --- Document Chunking ---
  chunking:
    strategy: recursive           # fixed | recursive | sentence | semantic
    chunk_size: 512               # Characters per chunk
    overlap: 50                   # Overlap between chunks

    # For recursive strategy: separator hierarchy
    separators:
      - "\n\n"
      - "\n"
      - ". "
      - " "

  # --- Embedding Generation ---
  embeddings:
    provider: ollama              # ollama | hf | sentence_transformers
    model: "nomic-embed-text"
    endpoint: "http://ollama:11434"
    dimension: 768                # Embedding vector dimension

  # --- Vector Store ---
  vector_store:
    backend: pgvector             # pgvector | chromadb | qdrant | faiss
    connection:                   # For pgvector:
      host: postgres
      port: 5432
      database: astromesh
      user: astromesh
      password: astromesh
    collection: product_docs      # Collection/table name

  # --- Reranking (optional) ---
  reranking:
    enabled: true
    provider: cross_encoder       # cross_encoder | cohere
    model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k: 5                     # Results after reranking

  # --- Retrieval Settings ---
  retrieval:
    top_k: 20                    # Initial candidates from vector search
    similarity_threshold: 0.7    # Minimum similarity score
```

### Chunking Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| `fixed` | Fixed character count with overlap | Uniform documents |
| `recursive` | Split by separator hierarchy | Structured text (markdown, code) |
| `sentence` | Split at sentence boundaries | Prose and articles |
| `semantic` | Split by embedding similarity | Mixed-format documents |

### Embedding Providers

| Provider | Description | Requires |
|----------|-------------|----------|
| `ollama` | Ollama embeddings endpoint | Running Ollama instance |
| `hf` | HuggingFace Inference API | HF API endpoint |
| `sentence_transformers` | Local SentenceTransformers | `pip install sentence-transformers` |

### Vector Stores

| Backend | Description | Requires |
|---------|-------------|----------|
| `pgvector` | PostgreSQL with pgvector extension | PostgreSQL + pgvector |
| `chromadb` | ChromaDB vector database | `pip install chromadb` |
| `qdrant` | Qdrant vector search engine | Qdrant server |
| `faiss` | Facebook AI Similarity Search | `pip install faiss-cpu` |

---

## Channel Configuration

**File location:** `config/channels.yaml`

Defines external messaging platform integrations. Each channel connects incoming messages to an Astromesh agent.

```yaml
channels:
  whatsapp:
    # WhatsApp Business Cloud API credentials (use environment variables)
    verify_token: "${WHATSAPP_VERIFY_TOKEN}"
    access_token: "${WHATSAPP_ACCESS_TOKEN}"
    phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
    app_secret: "${WHATSAPP_APP_SECRET}"

    # Which agent handles WhatsApp conversations
    default_agent: "whatsapp-assistant"

    # Rate limiting for outgoing messages
    rate_limit:
      window_seconds: 60
      max_messages: 30
```

### WhatsApp Environment Variables

| Variable | Description |
|----------|-------------|
| `WHATSAPP_VERIFY_TOKEN` | Token used to verify the Meta webhook during setup |
| `WHATSAPP_ACCESS_TOKEN` | Permanent access token from Meta Business settings |
| `WHATSAPP_PHONE_NUMBER_ID` | Phone number ID from the WhatsApp Business account |
| `WHATSAPP_APP_SECRET` | App secret used to validate incoming webhook signatures |

The `default_agent` must match the `metadata.name` of an agent defined in `config/agents/`. The `rate_limit` section controls outgoing message throttling to stay within WhatsApp API limits.

---

## Runtime Configuration

**File location:** `config/runtime.yaml`
**Kind:** `RuntimeConfig`

Global settings for the Astromesh runtime.

```yaml
apiVersion: astromesh/v1
kind: RuntimeConfig
metadata:
  name: default

spec:
  api:
    host: "0.0.0.0"
    port: 8000

  defaults:
    orchestration:
      pattern: react              # Default pattern for agents that don't specify one
      max_iterations: 10
```

---

## Configuration Tips

### Environment Variables

Sensitive values like API keys should be referenced by environment variable name, never hardcoded:

```yaml
api_key_env: OPENAI_API_KEY    # The agent reads os.environ["OPENAI_API_KEY"]
```

### File Naming Conventions

| Resource | Pattern | Example |
|----------|---------|---------|
| Agent | `<name>.agent.yaml` | `support-agent.agent.yaml` |
| RAG Pipeline | `<name>.rag.yaml` | `product-knowledge.rag.yaml` |
| Providers | `providers.yaml` | `providers.yaml` |
| Runtime | `runtime.yaml` | `runtime.yaml` |

### Directory Structure

```
config/
├── runtime.yaml              # Global runtime settings
├── providers.yaml            # Provider registry
├── channels.yaml             # Channel integrations (WhatsApp, etc.)
├── agents/
│   ├── support-agent.agent.yaml
│   ├── sales-qualifier.agent.yaml
│   ├── whatsapp-assistant.agent.yaml
│   └── code-reviewer.agent.yaml
└── rag/
    ├── product-knowledge.rag.yaml
    └── internal-docs.rag.yaml
```

### Multiple Environments

Use separate config directories for different environments:

```bash
# Development
ASTROMESH_CONFIG_DIR=./config/dev uv run uvicorn astromesh.api.main:app

# Production
ASTROMESH_CONFIG_DIR=./config/prod uv run uvicorn astromesh.api.main:app
```

### Docker Override

Mount your config directory into the container:

```yaml
# docker-compose.override.yaml
services:
  astromesh:
    volumes:
      - ./my-configs:/app/config
```
