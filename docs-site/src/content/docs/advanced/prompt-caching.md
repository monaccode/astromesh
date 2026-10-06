---
title: Prompt Caching
description: Keep an agent's prompt prefix stable so providers that cache by prefix can serve it from cache
---

Kimi/Moonshot (via `openai_compat`), OpenAI, vLLM and llama.cpp cache prompts **automatically by prefix**: tokens at the start of a request that match a previous request are served from cache at reduced cost and latency. There is nothing to enable. Your job is to not break the prefix.

The rule: **everything before the last message must be identical between calls.** Since v0.64.0 the runtime sends the prompt in this order:

```
system → tools → history (as messages) → [glyph grammar] → prompts.context + query
```

Only the last message changes per turn. Anything that varies earlier in the list invalidates the cache from that point on, including the tools and history that follow it.

## What breaks the prefix

### 1. History rendered inside the system prompt

Iterating `memory.conversation` in `prompts.system` makes the system change every turn.

```yaml
# Before: the system changes on every turn
prompts:
  system: |
    You are a support agent.
    {% for t in memory.conversation %}{{ t.role }}: {{ t.content }}
    {% endfor %}
```

```yaml
# After: remove it, the history arrives as messages
prompts:
  system: |
    You are a support agent.
memory:
  conversational:
    strategy: sliding_window
    max_turns: 20
```

When the agent declares `memory.conversational` and uses the `react` or `glyph` pattern, history reaches the model as messages. The runtime detects the legacy template (regex `memory\.conversation\b`), keeps it working without duplicating the history, and logs a warning at load. Do not iterate `memory.conversation` inside `prompts.context` either: the model would see the history twice.

### 2. Per-turn data in the system prompt

`knowledge` (RAG), `prefetch`, `memory.semantic`, `memory.episodic` and fields of the current message (for example a quoted reply) change with every query. Move them to `prompts.context`, which the runtime prepends to the current user message.

```yaml
# Before: the system changes on every query
prompts:
  system: |
    You are a sales analyst.
    {% if knowledge %}RELEVANT DOCUMENTS:
    {{ knowledge }}{% endif %}
```

```yaml
# After: stable system, per-turn data next to the query
prompts:
  system: |
    You are a sales analyst. Answer with the data you are given.
  context: |
    {% if knowledge %}RELEVANT DOCUMENTS:
    {{ knowledge }}{% endif %}
    {% if prefetch.stock %}CURRENT STOCK: {{ prefetch.stock }}{% endif %}
```

The turn stored in memory is the original query, without the context block, so RAG output does not pile up in history.

The load warning looks **only inside Jinja blocks** (`{{ }}` / `{% %}`); prose such as "use the knowledge base" does not trigger it. A conditional that is stable within a session (for example one that depends on who is writing) can safely stay in the system prompt. The warning will still fire for it. That is expected: it cannot tell stable from per-query.

`prompts.context` is only separated from the system by the `react` and `glyph` patterns. With other patterns it is appended to the end of the system prompt, which gives no cache gain, and a warning is logged at load.

## Budget interaction

- `prompts.context` tokens count against the history budget, because they occupy the window.
- When the budget trims history it drops the oldest turn, which shifts the prefix. A `prompts.context` whose size swings widely can make the oldest turn go in and out. Keep it bounded.
- Without `context_window` (and no Ollama `num_ctx` or litellm knowledge of the model) the history is not trimmed by budget, only by `max_turns`, and the agent warns at load. Declare `context_window` on the model candidate to activate the budget.

See [Agent YAML](/astromesh/configuration/agent-yaml/) for `prompts.context`, `context_window` and memory strategies, and the [Memory Manager](/astromesh/reference/core/memory-manager/) and [Runtime Engine](/astromesh/reference/core/runtime-engine/) references.

## Measuring

Two spans tell you whether the cache is working (see [Observability](/astromesh/advanced/observability/)):

- `llm.complete` carries `cache.hit_ratio` (`cached_tokens / input_tokens`).
- `context_fit` (child of `prompt_render`) carries `history.delivery` (`messages` or `template`), `turn_context.delivery` (`message`, `system` or `none`) and `history.budget` (`-1` means unbounded).

A healthy second turn shows `history.delivery=messages`, `turn_context.delivery=message` (if you use `prompts.context`) and `cache.hit_ratio` above 0. Moonshot caches in blocks of 4096 tokens, so a short prompt can legitimately show 0. Measured against Moonshot on 2026-09-04, a stable prefix reached 86-88% of the prompt cached.

If `history.delivery=template`, the legacy template is still in place. If `turn_context.delivery=system`, the pattern does not separate the context.

## Migrating published agents

A manifest change only takes effect when the agent is republished. After deploying a runtime that includes these changes, republish your existing agents so they pick up the new manifests.

## Checklist

- [ ] `prompts.system` has no `memory.conversation`, `knowledge`, `prefetch` or `memory.semantic/episodic` inside Jinja blocks.
- [ ] Per-turn data lives in `prompts.context`, kept bounded.
- [ ] The agent declares `memory.conversational` and uses `react` or `glyph`.
- [ ] `context_window` is set on the model candidate.
- [ ] No load warnings you did not expect.
- [ ] Second turn: `history.delivery=messages` and `cache.hit_ratio` > 0.
- [ ] Published agents were republished.
