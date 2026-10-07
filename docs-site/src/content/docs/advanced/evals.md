---
title: Agent Evals
description: Run cases against an agent with stubbed tools and isolated memory, and fail CI when quality or cost crosses a threshold
---

An eval is a `*.eval.yaml` file that runs cases against an agent in the same config tree and fails below a threshold. Use it as a gate before you change a prompt, a model or the context budget: it reports quality and cost side by side, so a cheaper prompt that answers worse shows up as a failure, not as a saving. Available since v0.67.0.

```bash
uv run astromesh-eval config/ --out report.json
```

Without file arguments it runs every `config/evals/*.eval.yaml`. Exit codes:

| Code | Meaning |
|---|---|
| `0` | Every eval met its thresholds |
| `1` | At least one eval fell below a threshold |
| `2` | Load error (invalid or unreadable YAML, unknown agent, an agent tree that does not boot). No case runs. |

## Format

```yaml
apiVersion: astromesh/v1
kind: Eval
metadata:
  name: lucia-basic
spec:
  agent: lucia                  # an agent from the same config tree
  judge:                        # optional; only cases with a rubric use it
    model: {provider: openai_compat, model: kimi-k2, endpoint: "https://api.moonshot.ai/v1", api_key_env: MOONSHOT_API_KEY}
    pass_score: 0.7             # default 0.7
  tools_default: real           # real | block
  thresholds:
    pass_rate: 0.9              # required: share of cases that must pass
    max_avg_tokens: 6000        # optional: average tokens_in + tokens_out per case
  cases:
    - id: stock-simple
      turns:
        - "How much stock is there of X?"
      context: {prefetch: {stock: 12}}
      tools:
        check_stock: {sku: X, stock: 12}
      expect:
        - contains: "12"
        - tool_called: check_stock
        - not_contains: "I don't know"
      rubric: "Answers with the quantity and does not make up prices."
  cases_file: lucia.cases.jsonl # optional, relative to the eval; one case per line, same shape
```

Editors validate it against `vscode-extension/schemas/eval.schema.json`. The runner does its own validation and does not need `jsonschema` installed.

### Cases

- `id` is required, unique within the eval, `[a-z0-9_-]{1,64}`.
- `turns` is one or more user messages. They share one session, so a case can test memory across turns.
- `context` is the same dict `/v1/agents/{name}/run` accepts, sent on every turn.
- A case needs `expect`, `rubric` or both; one with neither cannot fail and is a load error.

### Assertions

`expect` is checked against the **last turn's answer**, except `tool_called` and `tool_not_called`, which look at **every** tool call in the case.

| Assertion | Passes when |
|---|---|
| `contains` | the text appears in the answer, case-insensitive |
| `not_contains` | it does not appear, case-insensitive |
| `regex` | `re.search` finds a match (case-sensitive; use `(?i)` for insensitive) |
| `equals` | the stripped answer is identical |
| `tool_called` | the tool was called at least once |
| `tool_not_called` | it was never called |

### Judge

A case with `rubric` is also graded by an LLM judge, built from `judge.model` like any model candidate. It returns a score from 0 to 1 and passes at `pass_score`. A judge that fails or answers with something other than a valid score leaves the case in `error`. Judge tokens are reported apart and never count toward `max_avg_tokens`.

## Tools and memory

- **Fixtures.** A tool listed under a case's `tools` is not executed; the model receives that value (a non-map value arrives as `{"result": value}`). The result still goes through the [tool result cap](/astromesh/configuration/agent-yaml/#tool-result-budget), and confirmation gates still apply. Fixtures match by tool name in every agent of the tree, so a sub-agent called as a tool is stubbed too.
- **`tools_default: block`.** A tool without a fixture returns `{"error": "tool sin fixture en el eval: <name>"}` instead of running. With `real` (the default) it runs for real, so use `block` for agents whose tools write.
- **Memory.** Conversational memory runs in-process for the whole eval: nothing is written to Redis or Postgres.

## Report

Each case ends `pass`, `fail` (an assertion or the judge said no; the reasons are listed) or `error` (the run raised, or the judge gave no valid verdict). `error` counts as not passed.

The console prints a table per eval and an aggregate line. `--out` writes JSON:

```json
{
  "run_id": "3f2a91c0",
  "evals": [{
    "name": "lucia-basic", "agent": "lucia", "passed": true,
    "pass_rate": 1.0, "avg_tokens": 2310.0, "total_cost": 0.0042,
    "cases": [{
      "id": "stock-simple", "status": "pass", "motivos": [],
      "judge": {"score": 0.9, "reason": "..."},
      "tokens_in": 2200, "tokens_out": 110, "cached_tokens": 1800,
      "cost": 0.0042, "latency_ms": 1830.4, "judge_tokens": 240,
      "tools_llamadas": ["check_stock"], "answer": "..."
    }]
  }]
}
```

`cached_tokens` is the part of `tokens_in` the provider served from its prefix cache, which is the number to watch when you move content into [`prompts.context`](/astromesh/advanced/prompt-caching/).
