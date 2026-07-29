---
title: Agent Chaining
description: Declare which agents fire when one finishes, and under which conditions, with spec.chain and spec.output_schema
---

An agent can declare, in its own YAML, which other agents to fire when it finishes -- and under which conditions.

```yaml
spec:
  output_schema:
    score: {type: integer}

  chain:
    on_complete:
      - agent: email-composer
        when: "{{ output.data.score > 7 }}"
```

Available since astromesh **v0.38.1**.

## Why not just a Workflow

A [`kind: Workflow`](/astromesh/reference/api-endpoints/) describes a sequence **from the outside**: someone else decides which agents chain together and in what order. That is the right tool when the process is the protagonist.

A chain lives **inside the agent**. The agent knows on its own who to wake up when it finishes, so you can reuse it anywhere without wrapping it in a workflow first. And because it compiles down to a `WorkflowSpec`, it runs on the same engine -- there are never two ways to execute the same thing.

Under the hood, `spec.chain` is compiled **when the runtime boots** into a synthetic workflow named `__chain__<agent>`. Three consequences follow:

- a cycle, an exceeded `max_depth`, or a missing agent **stop the runtime from starting**, with the full path in the message -- they do not fail halfway through a production run
- the expanded chain is **inspectable without executing anything** (`GET /v1/agents/{name}/chain`)
- the `__chain__` prefix is reserved: a hand-written workflow that uses it is rejected by the loader, so it can never silently shadow an agent's chain

## Full surface

```yaml
spec:
  chain:
    mode: sequential        # sequential | parallel   (default: sequential)
    max_depth: 5            # default: 5

    on_complete:
      - agent: email-composer
        when: "{{ output.data.score > 7 }}"
        input: "{{ output.answer }}"          # default: "{{ output.answer }}"
        retry:
          max_attempts: 3
          backoff: exponential                # fixed | exponential
          initial_delay_seconds: 2
        timeout_seconds: 30
        on_error: continue                    # stop (default) | continue | <agent>

      - agent: crm-logger                     # no `when` = always fires

      - agent: human-triage
        default: true                         # only if no `when` matched
```

### What fires

Rules are evaluated **all of them**, not as a cascade. For each one:

| shape | fires when |
|---|---|
| with `when` | the template renders `true`, `1` or `yes` |
| no `when`, no `default` | always |
| `default: true` | only if **no `when` rule in this chain** matched |

Rules without `when` **do not count as a match** for the purposes of `default`. In the example above, with `score = 2`:

- `email-composer` does not fire (its `when` was false)
- `crm-logger` fires (it has no `when`)
- `human-triage` fires as well, because no `when` matched

There can be at most one `default` rule, and it cannot carry a `when` -- declaring both is a startup error.

### `mode`: sequential or parallel

`mode` decides **when** the links that fired run, not which ones.

- `sequential` (default) -- one after another. Each `when` is evaluated right before dispatching its link, so it can read earlier results through `steps`.
- `parallel` -- all at once. **Every guard is evaluated up front, before any link starts**, against the previous agent's output.

That difference has a concrete consequence: under `parallel`, a `when` referencing a sibling would always be false. Rather than letting it fail silently, **the compiler rejects it at startup** and tells you to use `sequential`.

The `default` rule always runs as its own step after the fan-out, because it needs the sibling guards already evaluated to know whether it applies.

### Context available in `when` and `input`

| variable | contents |
|---|---|
| `output.answer` | the prose answer of the immediately preceding agent |
| `output.data` | object validated against its `output_schema`, or `None` |
| `output.steps` | that agent's orchestration steps |
| `trigger` | original payload: `query`, `session_id`, `context` |
| `steps` | outputs of links already executed, by name |
| `when` | boolean result of each guard already evaluated, by step name |

`output` always refers to the **immediately preceding agent in the chain**, not to the one that started it. In `A → B → C`, the `when` in B's chain sees B's output.

## `spec.output_schema`

Conditions are only trustworthy if there is something structured to condition on. That is what `output_schema` is for.

```yaml
spec:
  output_schema:            # shorthand, same as tool `parameters`
    score:  {type: integer}
    urgent: {type: boolean}
```

Full JSON Schema (`type: object` + `properties`) is also accepted, and is never rewritten behind your back.

**How it works.** No provider in the repo supports native `response_format` or `json_schema`, so the shape is requested through the prompt: the runtime appends an instruction asking the model to answer in prose and close with a ` ```json ` block. It then extracts that block (the last one, if there are several; or the whole answer if it is bare JSON), validates it, and places it in `result["data"]`.

**`answer` is left untouched**, prose and all. `data` is added alongside it, so existing consumers do not change.

**A validation failure does not abort the run.** `data` becomes `None`, the detail goes to `data_error`, and everything is recorded in the trace. A `when` depending on that field will fail *that link* with a message naming the cause. Retrying the agent because it emitted invalid JSON is not implemented.

### What the validator covers

It is a purpose-built validator with no dependencies -- `jsonschema` is not among the base dependencies, and promoting it would force re-locking three uv projects and add a dependency to the boot path of the Astromesh OS image.

**Supported:** `type` (`object`, `string`, `integer`, `number`, `boolean`, `array`, `null`), `properties`, `required`, `enum`, `items`.

**Ignored, silently:** `allOf`, `anyOf`, `oneOf`, `not`, `$ref`, `patternProperties`, `additionalProperties`, `format`, `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, `minItems`, `maxItems`, `uniqueItems`.

Ignoring rather than rejecting is deliberate: a schema using `oneOf` still validates the parts the module understands, instead of taking down the whole agent over one unknown keyword.

One detail that *is* enforced: **`true` does not pass as an `integer`**, even though `bool` subclasses `int` in Python.

## Strict conditions

Steps emitted by the compiler are evaluated with `StrictUndefined`. A `when` referencing a non-existent field **fails that link with an explicit message**, instead of rendering empty and behaving exactly like a false condition.

Hand-written workflows keep the historical (silent) behaviour unless the step declares `strict_conditions: true`. This is the same trap the repo's own example workflow fell into, where a `when` over `output.data.score` could never be true and fell through to the `default` without a trace.

## Errors

| situation | behaviour |
|---|---|
| link raises | `retry` applies; once exhausted it is marked `error` and `on_error` decides |
| `on_error` undeclared (default) | the chain stops |
| `on_error: continue` | the error is recorded and the chain proceeds |
| `on_error: <agent>` | jumps to that step |
| timeout | same as an exception; the message names the `timeout_seconds` |
| invalid `data` | `data = None` + `data_error`; does not stop anything by itself |
| cycle | pruned **at compile time**; startup error |
| `max_depth` exceeded | startup error naming the full path |
| missing agent | startup error naming the agent and who references it |

Under `parallel`, a failing branch does not take down its siblings if it declared `on_error: continue`.

**The invoked agent's `answer` is always returned**, whatever the chain's status. A link failing never invalidates an answer that was already produced.

## Recursion

If a link declares its own chain, that chain fires too. `A → B → C` emerges without anyone drawing the whole graph.

There are two brakes, and both act **at compile time**, not at runtime:

- `max_depth` (default 5)
- cycle detection: if an agent is already on the current path, it is not re-expanded

Both produce a startup error with the full path in the message.

## The response

```json
{
  "answer": "Lead qualified 8/10 -- budget confirmed...",
  "data":   {"score": 8, "urgent": true},
  "steps":  [],
  "trace":  {},
  "chain": {
    "run_id": "wf-9c2...",
    "status": "partial",
    "mode": "sequential",
    "links": [
      {"agent": "email-composer", "depth": 1, "via": null,
       "status": "success", "answer": "Sent to ana@acme.com",
       "data": {"sent": true}, "duration_ms": 812},
      {"agent": "crm-logger", "depth": 1, "via": null,
       "status": "error", "error": "timed out after 30s"}
    ]
  }
}
```

`chain.status`:

| value | meaning |
|---|---|
| `completed` | every link that fired finished cleanly |
| `partial` | there were errors but the chain continued |
| `failed` | a link stopped the chain |

`links[].status` is `success`, `error` (with `error`) or `skipped` (with `reason`: `condition_false`, `cycle`, `max_depth` or `upstream_stopped`).

**Links that did not fire also appear**, with `reason: condition_false`. It is more noise, but it is the only way to answer "why wasn't the email sent?" without digging through the trace.

An agent without a `chain` returns `chain: null` and its usual shape.

## Observability

The whole chain hangs off **a single trace tree** and shares the run's session.

```
GET /v1/agents/{name}/chain
```

Returns the expanded graph -- agents, conditions, depths, `via`. Because it is a compile-time artifact, you can request it without executing anything. Returns `404` if the agent does not exist or declares no chain.

## Workflow engine additions

The same release added four capabilities to `kind: Workflow`, each useful on its own:

- **`when` guard per step.** A Jinja condition that, when false, leaves the step `skipped` and continues. Unlike `switch` + `goto` (which runs one branch and ends the workflow), it lets several conditional steps coexist in one run.
- **`on_error: continue`.** Records the step's error and carries on, for optional side effects.
- **`parallel` step type.** Runs a list of sub-steps at once and merges their outputs into the context, each addressable by name. Sub-steps are full steps, so `when`, `retry`, `timeout_seconds` and `on_error` work per branch.
- **The engine is actually wired.** Until v0.38.0 the `WorkflowEngine` was never instantiated outside the tests: `/v1/workflows/` always returned an empty list and no workflow in `config/workflows/` ever ran.

## Out of scope

- asynchronous fire-and-forget dispatch (a `chain_run_id` you poll)
- retrying the agent when `output_schema` validation fails
- chains crossing nodes through `PeerClient` -- distributed choreography is its own design
- semantic conditions evaluated by an LLM (`when_llm`)
- a visual chain editor in Forge; only the endpoint that would enable it exists today

## Complete example

`config/agents/sales-qualifier.agent.yaml` in the repo declares an `output_schema` and a chain into `email-composer`. `config/workflows/example.workflow.yaml` covers the same case from the outside, with a `kind: Workflow`, so you can compare both approaches side by side.
