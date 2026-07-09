# Model roles per architecture + multi-source models (LiteLLM)

- **Date:** 2026-07-09
- **Status:** Design approved (pending user spec review)
- **Owner:** jc@fulfaro.dev

## Problem

Today each `Agent` builds **one** `ModelRouter` from `spec.model` (`primary` / `fallback` /
`extra`) and every orchestration pattern (ReAct, PlanAndExecute, ParallelFanOut, Pipeline,
Supervisor, Swarm) receives the **same** `model_fn`. Two consequences:

1. A pattern cannot pick a different model per decision point — e.g. a supervisor cannot use a
   strong model to plan and a cheap model for workers; PlanAndExecute cannot use a premium model
   to plan and a local model to execute steps.
2. Adding a new model **source** (Anthropic native, Gemini, Bedrock, Groq, Mistral, Azure…)
   requires hand-writing a provider adapter each time. Coverage is limited and manual.

This is a transversal feature: it touches the YAML schema, the runtime engine, the model-router
wiring, the provider layer, and every orchestration pattern.

## Goals

- Let an assistant declare **models from multiple sources** easily (evaluate/adopt a library).
- Let each orchestration pattern **choose the model per decision point** ("role").
- **Zero migration**: the 6 existing agents keep working untouched.
- Incremental, mergeable rollout — no big-bang; each step leaves the suite green.

## Non-goals

- Streaming role selection (patterns use `complete()` today; streaming path unchanged).
- Per-token dynamic model switching mid-message.
- Removing or rewriting the native providers.
- Updating the public documentation site until the feature ships (see Rollout step 5).

## Decisions (from brainstorming)

1. **Hybrid roles + strategy** — one `ModelRouter` per role (Option A below).
2. **Hybrid sources** — LiteLLM for the cloud long tail + native adapters (ollama/vllm/etc.),
   mixable as `candidates` within a single role.
3. **Optional roles with fallback to `default`** — patterns request roles by standard name; an
   undefined role falls back to `default` (which subsumes today's `primary`). Maximum backward
   compatibility.

## Architecture

### Key abstraction — one `ModelRouter` per role (Option A)

The engine builds a `dict[str, ModelRouter]` for the agent, one router per defined role
(`default`, `planner`, `worker`, …). Each router reuses the **existing** `ModelRouter`
unchanged: strategy ranking, circuit breaker, health/EMA, fallback across `candidates`.

Chosen over a single `RoleAwareRouter` because it reuses 100% of `ModelRouter` with zero risk to
the current path, and isolating the circuit breaker per role is desirable (a tripped `planner`
circuit must not affect `worker`). Cost: if the same model appears in several roles, several
stateless adapter instances are created — cheap.

### `model_fn` gains an optional `role`

The only transversal change to patterns: `model_fn` grows an optional `role` argument.

```python
# Agent (engine.py) builds this closure:
async def model_fn(messages, tools, role=None):
    resolved = self._role_map.get(role, role)          # optional role_map override
    router = self._routers.get(resolved) or self._routers["default"]
    return await router.route(messages, tools=tools, **route_kwargs)
```

`role` defaults to `None` → `default`. A pattern that is not updated behaves identically (all
traffic → `default`). Resolution order: `role_map[role]` → `roles[...]` → `default`.

Observability: add `role` (requested) and the resolved role as attributes on the `llm.complete`
span.

## YAML schema (`spec.model`)

Three shapes, all backward compatible. New shape:

```yaml
spec:
  model:
    default:                       # base model; anything without a specific role lands here
      candidates:
        - {source: ollama, model: "llama3.1:8b", endpoint: "http://localhost:11434"}
      strategy: cost_optimized     # optional, per role

    roles:                         # semantic per-role models
      planner:
        candidates:
          - {source: litellm, model: "anthropic/claude-opus-4-8", api_key_env: ANTHROPIC_API_KEY}
          - {source: litellm, model: "openai/gpt-4o"}   # fallback within the role
        strategy: quality_first
      worker:
        candidates:
          - {source: ollama, model: "llama3.1:8b"}
          - {source: litellm, model: "groq/llama-3.1-70b-versatile"}
        strategy: cost_optimized
```

### Candidate block

`{source, model, endpoint?, api_key_env?, api_key?, parameters?, timeout?}`

- `source: litellm` → `LiteLLMProvider` (anthropic, gemini, bedrock, groq, mistral, azure…). The
  `model` carries the LiteLLM prefix (`anthropic/…`, `gemini/…`).
- `source: ollama | openai_compat | vllm | hf | llamacpp | onnx` → existing native adapters.
- If `source` is omitted: infer `litellm` when the model has a known LiteLLM prefix, else
  `openai_compat` (current behaviour).

### Backward-compat normalization (in the engine, no YAML migration)

- `model.primary`  → first candidate of role `default`.
- `model.fallback` → second candidate of role `default`.
- `model.extra.{name}` → additional candidates of role `default`.
- `model.routing.strategy` → `strategy` of role `default`.

A dedicated test asserts the old shape normalizes to an identical `default` router, guaranteeing
the 6 existing agents run unchanged.

### Optional escape hatch — `role_map`

```yaml
orchestration:
  pattern: plan_and_execute
  role_map: {synthesizer: planner}   # use 'planner' wherever the pattern asks for 'synthesizer'
```

## Pattern → role vocabulary

Standard role names each pattern requests (undefined → `default`):

| Pattern          | Decision point → role |
|------------------|-----------------------|
| ReAct            | reasoning loop → `reasoner` |
| PlanAndExecute   | build plan → `planner`; execute step → `worker`; final synthesis → `synthesizer` |
| ParallelFanOut   | decompose → `planner`; subtasks → `worker`; aggregate → `synthesizer` |
| Pipeline         | each stage → `stage:<name>`, falling back to `worker` |
| Supervisor       | coordination/decision → `supervisor` (workers are sub-agents via `tool_fn`, with their own `model`) |
| Swarm            | each agent's reasoning → `reasoner` (confirm against `swarm.py` at implementation) |

Role names are intentionally reused across patterns: define `worker` once and it applies wherever
it makes sense.

## `LiteLLMProvider`

Implements `ProviderProtocol` identically to `OpenAICompatProvider`:

- **Optional dependency** in `pyproject.toml`: `litellm = ["litellm>=1.50.0"]`, added to `all`.
  `import litellm` is lazy (inside `__init__`/`complete`). If the dep is missing and a candidate
  requests `source: litellm`, the engine logs a warning and **skips that candidate** (others in
  the role still register) — same behaviour as today's unknown-provider path. Nothing breaks
  without LiteLLM installed.
- `complete()` → `await litellm.acompletion(model=..., messages=..., tools=..., **params)`. Reuse
  `_normalize_tool_calls` (LiteLLM returns nested OpenAI tool-call shape) and map `usage` →
  `{input_tokens, output_tokens, cache_read_input_tokens}`. Preserve `reasoning_content`
  (matters for the Kimi flow).
- `estimated_cost()` → `litellm.completion_cost(...)` / `cost_per_token(...)` — LiteLLM maintains
  the pricing table for 100+ models, removing the hand-maintained `PRICING` map for cloud models.
- `provider` label → derived from the model prefix (`anthropic/…` → `anthropic`).
- `supports_tools` / `supports_vision` → `litellm.supports_function_calling(model)` /
  `supports_vision(model)`.
- Auth: `api_key` / `api_key_env` exported to the env LiteLLM expects, or passed as `api_key=`.

## Components changed

| Unit | Change | Purpose / interface |
|------|--------|---------------------|
| `providers/litellm_provider.py` (new) | `LiteLLMProvider(ProviderProtocol)` | Unified cloud multi-source access via LiteLLM. |
| `runtime/engine.py` `_register_model_providers` | Build per-role routers; add `source`-aware candidate builder; normalize legacy schema | Produce `dict[str, ModelRouter]`. |
| `runtime/engine.py` `Agent` | Hold `_routers` dict + `_role_map`; `model_fn(role=...)` resolution; span attrs | Route by role. |
| `orchestration/patterns.py` + `supervisor.py` + `swarm.py` | Pass role names at decision points | Adopt role vocabulary. |
| `pyproject.toml` | `litellm` optional extra | Optional dependency. |

## Error handling

- Missing LiteLLM dep for a `litellm` candidate → warn + skip candidate (role keeps others).
- Role with zero registerable candidates → warn; requests to that role fall back to `default`.
- `default` role with zero candidates → existing "no providers registered" warning path.
- Per-role circuit breaker isolation preserved by construction (separate `ModelRouter` instances).

## Testing

- `LiteLLMProvider`: monkeypatch `litellm.acompletion` / `completion_cost` (no network). Assert
  tool-call normalization, usage mapping, cost, `reasoning_content` passthrough.
- **Schema normalization**: old `primary/fallback/extra/routing` produces an identical `default`
  router (backward-compat guarantee for the 6 agents).
- **Role resolution**: `model_fn(role="planner")` hits the planner router; undefined role →
  default; `role_map` remaps.
- **Per pattern** (mocked routers): PlanAndExecute uses `planner`/`worker`/`synthesizer`; ReAct
  uses `reasoner`; assert the right router is invoked at each decision point.
- Per-role circuit breaker isolation.

## Rollout (incremental, each step mergeable and green)

1. `LiteLLMProvider` + `source`-aware candidate builder (broaden sources; patterns untouched).
2. Legacy-schema normalization + `default`/`roles` parsing → `dict[str, ModelRouter]` on the
   `Agent`; `model_fn(role=...)`.
3. Update patterns one by one to pass their role vocabulary (start with PlanAndExecute and
   Supervisor — highest value).
4. CHANGELOG entry (per the changelog rule) + an example agent YAML using roles.
5. **Last:** update the public docs site (`configuration/providers.md`,
   `configuration/agent-yaml.md`, `reference/core/model-router.md`) in present tense — only after
   the runtime ships the feature and tests are green.
