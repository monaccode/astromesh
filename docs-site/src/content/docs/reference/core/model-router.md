---
title: Model Router
description: Multi-provider routing with circuit breaker and fallback
---

The Model Router selects which LLM provider handles each request based on configurable routing strategies, with automatic fallback and circuit breaker protection. It lives in `astromesh/core/model_router.py`.

## Routing Overview

```
                    Incoming Request
                         │
                         ▼
              ┌──────────────────────┐
              │   Routing Strategy   │
              │  (cost / latency /   │
              │   quality / round    │
              │   robin / capability)│
              └──────────┬───────────┘
                         │
              ┌──────────▼──────────┐
              │  Circuit Breaker    │
              │  State Check        │
              │  (closed? open?     │
              │   half-open?)       │
              └──────────┬──────────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
     ┌───────────┐ ┌───────────┐ ┌───────────┐
     │  OpenAI   │ │ Anthropic │ │  Ollama   │
     │ Provider  │ │ Provider  │ │ Provider  │
     └───────────┘ └───────────┘ └───────────┘
            │            │            │
            └────────────┼────────────┘
                         │
                   On failure
                         │
                         ▼
              ┌──────────────────────┐
              │  Fallback Provider   │
              └──────────────────────┘
```

## Routing Strategies

Configure the strategy in your agent YAML under `spec.model.routing`:

```yaml
spec:
  model:
    primary:
      provider: openai
      model: gpt-4o
    fallback:
      provider: anthropic
      model: claude-sonnet-4-20250514
    routing: cost_optimized
```

| Strategy | Behavior | When to Use |
|----------|----------|-------------|
| `cost_optimized` | Selects the provider with the lowest `estimated_cost()` for the request | Budget-sensitive workloads, high-volume batch processing |
| `latency_optimized` | Selects the provider with the lowest `avg_latency_ms` | Real-time applications, chat UIs, latency-critical paths |
| `quality_first` | Always uses the primary provider; falls back only on failure | Tasks requiring the best model regardless of cost or speed |
| `round_robin` | Distributes requests evenly across all healthy providers | Load balancing, even utilization across providers |
| `capability_match` | Selects based on required capabilities (tools, vision, streaming) | Mixed workloads where some requests need tool calling and others need vision |

## Circuit Breaker

Each provider has an independent circuit breaker that prevents cascading failures.

### States

```
          success
    ┌──────────────┐
    │              │
    ▼              │
┌────────┐   3 failures     ┌────────┐   60s cooldown    ┌────────────┐
│ Closed │ ──────────────▶ │  Open  │ ───────────────▶  |  Half-Open │
└────────┘                  └────────┘                   └────────────┘
    ▲                                                       │
    │              success                                  │
    └───────────────────────────────────────────────────────┘
                                │
                           failure ──▶ Back to Open
```

| State | Behavior |
|-------|----------|
| **Closed** | Requests pass through normally. Failure counter incremented on each error |
| **Open** | All requests immediately rejected (no network call). Entered after 3 consecutive failures |
| **Half-Open** | Entered after 60-second cooldown. Allows a single probe request through. Success -> Closed, Failure -> Open |

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `failure_threshold` | `3` | Consecutive failures before circuit opens |
| `cooldown_seconds` | `60` | Seconds to wait before half-open probe |

## Per-role Routers

An agent is not limited to a single `ModelRouter`. When `spec.model` declares `default`/`roles` (see [Per-role Models](/astromesh/configuration/agent-yaml/#per-role-models)), the runtime builds one independent `ModelRouter` instance per role — each with its own strategy, its own registered providers, and its own circuit breaker state. A failure streak against the `worker` role's provider does not affect the `planner` role's circuit breaker; the two are fully isolated.

Orchestration patterns select which router to use by requesting a named `role` on every model call:

```python
response = await model_fn(messages, tools, role="planner")
```

`model_fn` resolves the role to a router in this order:

1. `role_map[role]` — if `spec.orchestration.role_map` remaps the requested role, use the mapped name.
2. Look up the resolved name in the agent's role routers (built from `spec.model.roles`).
3. Fall back to the `default` router if no router is registered under the resolved name.

Agents that only define legacy `primary`/`fallback` (or omit `role` entirely) get a single `default` router — the multi-router behavior is purely additive and does not change existing agents.

## ProviderProtocol

All LLM providers implement this runtime-checkable Protocol defined in `astromesh/providers/base.py`. The Model Router interacts with providers exclusively through this interface.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `complete()` | `async def complete(messages, tools?, temperature?, max_tokens?) -> CompletionResponse` | Send a chat completion request. Returns the full response when complete |
| `stream()` | `async def stream(messages, tools?, temperature?, max_tokens?) -> AsyncIterator[StreamChunk]` | Stream a chat completion. Yields chunks as they arrive |
| `health_check()` | `async def health_check() -> bool` | Verify the provider is reachable and authenticated. Returns `True` if healthy |
| `supports_tools()` | `def supports_tools() -> bool` | Whether this provider supports function/tool calling |
| `supports_vision()` | `def supports_vision() -> bool` | Whether this provider supports image inputs |
| `estimated_cost()` | `def estimated_cost(input_tokens: int, output_tokens: int) -> float` | Estimated cost in USD for a request of the given size. Used by `cost_optimized` routing |
| `avg_latency_ms` | `@property avg_latency_ms -> float` | Rolling average latency in milliseconds. Used by `latency_optimized` routing |

### CompletionResponse

| Field | Type | Description |
|-------|------|-------------|
| `content` | `str` | The model's text response |
| `tool_calls` | `list[ToolCall] \| None` | Tool calls requested by the model |
| `usage` | `TokenUsage` | Input/output token counts |
| `model` | `str` | Model identifier that actually served the request |
| `provider` | `str` | Provider name |

## Fallback Behavior

When the primary provider fails (network error, rate limit, circuit breaker open), the router automatically tries the fallback provider if configured:

1. Primary provider called
2. If primary fails or circuit breaker is open, log warning
3. Try fallback provider
4. If fallback also fails, raise `ProviderUnavailableError`

Both primary and fallback have independent circuit breakers. If both circuits are open, the request fails immediately without any network call.

## Agent YAML Configuration

```yaml
spec:
  model:
    primary:
      provider: openai
      model: gpt-4o
      temperature: 0.7
      max_tokens: 4096
    fallback:
      provider: anthropic
      model: claude-sonnet-4-20250514
      temperature: 0.7
      max_tokens: 4096
    routing: cost_optimized
```

| Field | Required | Description |
|-------|----------|-------------|
| `primary.provider` | Yes | Provider name (`openai`, `anthropic`, `ollama`, etc.) |
| `primary.model` | Yes | Model identifier for the provider |
| `primary.temperature` | No | Sampling temperature (0.0 -- 2.0). Default: provider-specific |
| `primary.max_tokens` | No | Maximum output tokens. Default: provider-specific |
| `fallback.provider` | No | Fallback provider name |
| `fallback.model` | No | Fallback model identifier |
| `routing` | No | Routing strategy. Default: `quality_first` |
