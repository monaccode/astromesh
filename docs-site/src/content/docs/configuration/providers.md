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
