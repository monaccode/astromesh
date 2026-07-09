---
title: Provider Configuration
description: Configure LLM providers, routing, and circuit breaker
---

The provider configuration defines which LLM backends are available to Astromesh, how to connect to them, and how the model router selects between them. All providers are declared in a single file and shared across all agents.

## File Location

Provider configuration lives at `config/providers.yaml` (development) or `/etc/astromesh/providers.yaml` (production).

```yaml
apiVersion: astromesh/v1
kind: ProviderConfig
metadata:
  name: default-providers
```

## Full Example

Below is a complete `providers.yaml` with all six provider types configured:

```yaml
apiVersion: astromesh/v1
kind: ProviderConfig
metadata:
  name: default-providers

spec:
  providers:
    # --- Ollama (local inference) ---
    ollama:
      type: ollama
      endpoint: "http://ollama:11434"
      models:
        - "llama3.1:8b"
        - "llama3.1:70b"
        - "codellama:34b"
        - "nomic-embed-text"
      health_check_interval: 30

    # --- OpenAI-compatible API ---
    openai:
      type: openai_compat
      endpoint: "https://api.openai.com/v1"
      api_key_env: OPENAI_API_KEY
      models:
        - "gpt-4o"
        - "gpt-4o-mini"

    # --- vLLM (high-throughput serving) ---
    vllm:
      type: vllm
      endpoint: "http://vllm:8000"
      models:
        - "mistralai/Mistral-7B-Instruct-v0.3"
      health_check_interval: 30

    # --- llama.cpp server ---
    llamacpp:
      type: llamacpp
      endpoint: "http://llamacpp:8080"
      models:
        - "local-model"

    # --- HuggingFace Text Generation Inference ---
    hf_tgi:
      type: hf_tgi
      endpoint: "http://tgi:80"
      models:
        - "BAAI/bge-small-en-v1.5"

    # --- ONNX Runtime (local) ---
    onnx:
      type: onnx
      models:
        - "model.onnx"

  routing:
    default_strategy: cost_optimized
    fallback_enabled: true
    circuit_breaker:
      failure_threshold: 3
      recovery_timeout: 60
```

## Provider Types

### Ollama

Ollama provides local LLM inference with simple model management. It is the recommended provider for development and single-node deployments.

**Setup:**

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start the Ollama server
ollama serve

# Pull models
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

**Configuration:**

```yaml
ollama:
  type: ollama
  endpoint: "http://localhost:11434"
  models:
    - "llama3.1:8b"
    - "nomic-embed-text"
  health_check_interval: 30
```

The endpoint is the Ollama HTTP API. When running in Docker, use the service name (e.g., `http://ollama:11434`). The `models` list declares which models this provider serves — it does not automatically pull them.

### OpenAI-Compatible

Any API that implements the OpenAI chat completions interface. Works with OpenAI, Azure OpenAI, Anthropic (via proxy), Together AI, Groq, and other compatible services.

**Setup:**

```bash
# Set your API key as an environment variable
export OPENAI_API_KEY="sk-..."
```

**Configuration:**

```yaml
openai:
  type: openai_compat
  endpoint: "https://api.openai.com/v1"
  api_key_env: OPENAI_API_KEY
  models:
    - "gpt-4o"
    - "gpt-4o-mini"
```

The `api_key_env` field is the name of the environment variable — not the key itself. The runtime reads the key from `os.environ["OPENAI_API_KEY"]` at startup. For Azure OpenAI, point the endpoint to your Azure deployment URL.

### Moonshot / Kimi

Moonshot's Kimi models (`kimi-k2.5`, `kimi-k2.6`) are served through the same `openai_compat` provider type — the Moonshot API implements the OpenAI chat-completions interface. No dedicated provider type is needed; you only change the endpoint, API key, and model names.

**Setup:**

```bash
# Set your Moonshot API key
export MOONSHOT_API_KEY="sk-..."
```

**Configuration:**

```yaml
kimi:
  type: openai_compat
  endpoint: "https://api.moonshot.ai/v1"
  api_key_env: MOONSHOT_API_KEY
  models:
    - "kimi-k2.5"
    - "kimi-k2.6"
```

Kimi models are labelled `kimi` (rather than `openai_compat`) in cost reports and metrics — the provider label is derived from the model name, so `by_provider` breakdowns and the `provider` Prometheus label separate Kimi traffic from OpenAI traffic automatically. See [Provider Labels](#provider-labels) below.

#### Thinking Models (`reasoning_content`)

Kimi k2.5 / k2.6 are **thinking models**: when reasoning is enabled they return a `reasoning_content` field alongside `tool_calls`, and the API **requires** that field to be echoed back on the assistant tool-call message in the next turn. If it is dropped, the API rejects the follow-up request with:

```
400 Bad Request — thinking is enabled but reasoning_content is missing in assistant tool call message
```

Astromesh handles this transparently:

- `CompletionResponse` carries a `reasoning_content` field, populated by `OpenAICompatProvider.complete()` from the response.
- The `ReActPattern` echoes `reasoning_content` back on the assistant message when it is present, so multi-turn tool calls against a thinking model work out of the box.
- For non-thinking models the field is absent and is simply omitted, so their behaviour is unchanged.

No configuration is required — this is automatic for any model that returns `reasoning_content`.

### vLLM

vLLM is a high-throughput LLM serving engine with continuous batching. Best for production workloads that need to serve many concurrent requests.

**Setup:**

```bash
# Run vLLM with Docker (requires NVIDIA GPU)
docker run --gpus all \
  -p 8000:8000 \
  vllm/vllm-openai:latest \
  --model mistralai/Mistral-7B-Instruct-v0.3
```

**Configuration:**

```yaml
vllm:
  type: vllm
  endpoint: "http://vllm:8000"
  models:
    - "mistralai/Mistral-7B-Instruct-v0.3"
  health_check_interval: 30
```

vLLM exposes an OpenAI-compatible API, but Astromesh uses the dedicated `vllm` provider type for optimized health checking and capability detection. GPU access is required.

### llama.cpp

llama.cpp provides lightweight CPU and GPU inference for GGUF-format models. Good for edge deployments and environments without dedicated GPU infrastructure.

**Setup:**

```bash
# Build and run the llama.cpp server
./llama-server -m /models/llama-3.1-8b.gguf --host 0.0.0.0 --port 8080
```

**Configuration:**

```yaml
llamacpp:
  type: llamacpp
  endpoint: "http://llamacpp:8080"
  models:
    - "local-model"
```

The model name in the `models` list is a logical identifier — the actual model file is specified when starting the llama.cpp server.

### HuggingFace TGI

HuggingFace Text Generation Inference (TGI) provides GPU-optimized transformer inference with features like flash attention and quantization.

**Setup:**

```bash
# Run TGI with Docker (requires NVIDIA GPU)
docker run --gpus all \
  -p 80:80 \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id BAAI/bge-small-en-v1.5
```

**Configuration:**

```yaml
hf_tgi:
  type: hf_tgi
  endpoint: "http://tgi:80"
  models:
    - "BAAI/bge-small-en-v1.5"
```

TGI is particularly useful for embedding models and specialized transformer architectures that benefit from HuggingFace's optimized inference stack.

### ONNX Runtime

ONNX Runtime runs optimized ONNX-format models locally without a network endpoint. Suited for scenarios where you need deterministic latency without network hops.

**Configuration:**

```yaml
onnx:
  type: onnx
  models:
    - "model.onnx"
```

No `endpoint` is needed — the model file is loaded directly by the runtime. The `models` list contains paths to `.onnx` files relative to the config directory.

### LiteLLM source (cloud multi-provider)

Cloud providers — Anthropic, Google Gemini, Groq, AWS Bedrock, Mistral, Azure — are reached through LiteLLM, a unified completion client, rather than through `config/providers.yaml`. LiteLLM is declared per-candidate inside an agent's `spec.model` block (see [Per-role Models](/astromesh/configuration/agent-yaml/#per-role-models)), not as a `providers.yaml` provider type.

**Install:**

```bash
uv sync --extra litellm      # just the LiteLLM extra
uv sync --extra all          # everything, including LiteLLM
```

LiteLLM is an **optional** dependency — the base install does not pull it in.

**Configuration:**

```yaml
spec:
  model:
    roles:
      planner:
        candidates:
          - {source: litellm, model: "anthropic/claude-opus-4-8", api_key_env: ANTHROPIC_API_KEY}
```

**Model-prefix convention:** the `model` string's prefix selects which cloud backend LiteLLM talks to:

| Prefix | Backend |
|--------|---------|
| `anthropic/…` | Anthropic (Claude) |
| `gemini/…` | Google Gemini |
| `groq/…` | Groq |
| `bedrock/…` | AWS Bedrock |
| `mistral/…` | Mistral |
| `azure/…` | Azure OpenAI (via LiteLLM) |

If a candidate omits `source`, Astromesh infers `litellm` whenever `model` contains a `/` (e.g. `anthropic/claude-opus-4-8`); a bare model name like `gpt-4o-mini` infers `openai_compat` instead.

**Auth:** `api_key_env` names the environment variable holding the API key (e.g. `ANTHROPIC_API_KEY`) — the key itself is never written to YAML.

**Skip-on-missing-install:** if a `source: litellm` candidate is configured but the `litellm` package is not importable, Astromesh logs a warning and skips *only that candidate*. Agent startup does not fail — other candidates in the same role, and every other role, still register normally.

## Provider Types Table

| Type | Description | Endpoint Format |
|------|-------------|-----------------|
| `ollama` | Ollama local inference server | `http://host:11434` |
| `openai_compat` | Any OpenAI-compatible API (OpenAI, Azure, Together, Groq, etc.) | `https://api.example.com/v1` |
| `vllm` | vLLM high-throughput serving engine | `http://host:8000` |
| `llamacpp` | llama.cpp server for GGUF models | `http://host:8080` |
| `hf_tgi` | HuggingFace Text Generation Inference | `http://host:80` |
| `onnx` | ONNX Runtime local inference | No endpoint needed |

## Routing

The routing section controls how the model router selects providers when an agent makes an inference request.

### Strategies

| Strategy | Value | When to Use |
|----------|-------|-------------|
| Cost Optimized | `cost_optimized` | Default. Prefers the cheapest available provider. Good for development and cost-sensitive workloads. |
| Latency Optimized | `latency_optimized` | Prefers the provider with the lowest response time. Good for real-time applications and chat interfaces. |
| Quality First | `quality_first` | Prefers the highest-capability model available. Good for complex reasoning tasks where accuracy matters most. |
| Round Robin | `round_robin` | Distributes requests evenly across all healthy providers. Good for load balancing across multiple identical deployments. |
| Capability Match | `capability_match` | Selects the provider based on request requirements (e.g., vision models for image inputs). Good for multi-modal agents. |

The `default_strategy` applies to all agents unless overridden in the agent's `spec.model.routing.strategy` field.

```yaml
routing:
  default_strategy: cost_optimized
```

### Fallback

When `fallback_enabled` is `true`, the model router automatically tries the next available provider if the primary fails. Agents can also define an explicit `fallback` model in their YAML.

```yaml
routing:
  fallback_enabled: true
```

### Circuit Breaker

The circuit breaker protects the system from repeatedly calling a failing provider. It tracks consecutive failures per provider and temporarily removes unhealthy providers from the routing pool.

```yaml
routing:
  circuit_breaker:
    failure_threshold: 3      # Open the circuit after 3 consecutive failures
    recovery_timeout: 60      # Wait 60 seconds before trying the provider again
```

**How it works:**

1. Each provider starts in the **closed** state (healthy, accepting requests).
2. When a request to a provider fails, the failure counter increments.
3. After `failure_threshold` consecutive failures (default: 3), the circuit **opens** — the provider is removed from the routing pool.
4. After `recovery_timeout` seconds (default: 60), the circuit enters a **half-open** state — the next request is sent to the provider as a test.
5. If the test request succeeds, the circuit **closes** and the provider is returned to the pool. If it fails, the circuit remains open for another recovery period.

## How Agents Reference Providers

Agents reference providers by the `type` value in their `spec.model.primary.provider` field. The model router looks up the matching provider in `providers.yaml`:

```yaml
# In providers.yaml
spec:
  providers:
    ollama:
      type: ollama
      endpoint: "http://ollama:11434"
      models:
        - "llama3.1:8b"
```

```yaml
# In an agent YAML
spec:
  model:
    primary:
      provider: ollama           # Matches the provider type above
      model: "llama3.1:8b"       # Must be in the provider's models list
      endpoint: "http://ollama:11434"
```

The agent's `endpoint` field can override the provider-level endpoint if needed (e.g., when an agent connects to a different Ollama instance).

## Model Pricing & Cost Estimation

The `openai_compat` provider ships a built-in per-model price table (USD per 1 000 tokens) used by `estimated_cost()` and the [cost tracker](/astromesh/advanced/observability/#cost-tracking). Every completion returns a `cost` computed from the response's token usage.

| Model | Input / 1K | Output / 1K | Cached input / 1K |
|-------|-----------|-------------|-------------------|
| `gpt-4o` | $0.0025 | $0.0100 | — |
| `gpt-4o-mini` | $0.000150 | $0.000600 | — |
| `gpt-4-turbo` | $0.0100 | $0.0300 | — |
| `gpt-4` | $0.0300 | $0.0600 | — |
| `gpt-3.5-turbo` | $0.0005 | $0.0015 | — |
| `kimi-k2.5` | $0.0006 | $0.0025 | $0.0001 |
| `kimi-k2.6` | $0.00095 | $0.0040 | $0.00016 |

Models not in the table estimate to `$0.00` — cost tracking only reflects models with known pricing. Kimi rates are cache-miss list prices; confirm them against your Moonshot account before relying on them for billing.

### Cache-Aware Pricing (Kimi context cache)

Moonshot's context cache bills tokens that hit the cache at a steep discount. When a response reports `cached_tokens` in its `usage` block, Astromesh splits the input cost:

- **Cached tokens** are priced at the model's cached-input rate (the `Cached input / 1K` column above).
- **Uncached tokens** (`input_tokens − cached_tokens`) are priced at the normal input rate.
- Output tokens are always billed at the full output rate.

```text
cost = (input_tokens − cached) / 1000 × input_price
     + cached                / 1000 × cache_price
     + output_tokens         / 1000 × output_price
```

`cached` is clamped to `[0, input_tokens]` (cached tokens are a subset of input). A model with no entry in the cache-price table falls back to its normal input rate, so there is no discount and no double-counting.

The cached-token count is also surfaced on the response so downstream consumers can see cache efficiency:

```python
response.usage
# {
#     "input_tokens": 12000,
#     "output_tokens": 800,
#     "cache_read_input_tokens": 9500   # tokens served from the context cache
# }
```

### Provider Labels

The `openai_compat` adapter serves OpenAI, Anthropic-compatible, and Moonshot/Kimi endpoints through a single class, but it does not receive an explicit provider identifier. Astromesh derives a stable **provider label** from the model name so cost reports and metrics can attribute traffic correctly:

| Model prefix | Provider label |
|--------------|----------------|
| `kimi…`, `moonshot…` | `kimi` |
| `claude…` | `anthropic` |
| `gpt…`, `o1…`, `o3…`, `o4…`, `chatgpt…` | `openai` |
| anything else | `openai_compat` |

This label is what appears in the `by_provider` cost breakdown and in the `provider` label on Prometheus metrics.
