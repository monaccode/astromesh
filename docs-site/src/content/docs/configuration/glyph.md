---
title: Glyph — Action Language
description: Write an agent's plan as a program instead of a tool-calling loop, with pattern glyph and spec.program
---

Glyph is an orchestration pattern where the agent's plan is **a program** the runtime
executes, instead of a loop that asks the model for one action at a time.

```yaml
spec:
  orchestration:
    pattern: glyph
    narrate: false
  program: |
    customer = find_customer(email=context.email)
    devices  = list_devices(customer_id=customer.id)
    active   = devices | where(active == true)
    warranty = active | map({g: check_warranty(sku=sku)})
    return {active, warranty}
```

Available since astromesh **v0.39.0**.

:::caution[Not on PyPI yet]
`astromesh-glyph` has not been published to PyPI yet, so `pip install
'astromesh[glyph]'` will fail — pip ignores `[tool.uv.sources]`. Inside the
monorepo it installs with `uv sync --extra glyph`. Tracked in
[`docs/DEBT.md`](https://github.com/monaccode/astromesh/blob/develop/docs/DEBT.md).
:::

## Read this first: Glyph is not a cost optimization

Glyph was built to save tokens by replacing several model round-trips with one
program. **That premise was measured against three models and did not hold.**

As a runtime pattern — the model writing the program on every run — Glyph costs
**+164% to +2839% more than ReAct**, and is slower in 16 of 17 measured runs. The
reason is structural: output tokens cost roughly 4x input tokens, and Glyph trades
cheap input for expensive output. Between 81% and 99% of its cost is the model
writing the program.

Where Glyph pays off is the opposite arrangement: **the model writes the program
once, a human reviews it, and the runtime executes it forever after with zero model
calls.** That is what `spec.program` is for, and it is the mode this page
recommends.

The full numbers, the benchmark, and how to measure your own case live in
[`docs/GLYPH_GUIDE.md`](https://github.com/monaccode/astromesh/blob/develop/docs/GLYPH_GUIDE.md)
in the repository.

## The language

Five constructs and nothing else.

```glyph
v = search_parts(make="Toyota", part="brake pads")   # call, arguments by name

oem = v | where(kind == "oem") | top(3, by=rating)   # pipe over a collection
alt = v | where(kind == "aftermarket", stock > 0)

if oem.empty:                                        # 4-space indented block
    eta = check_restock(sku=v.first.sku)

return {oem, alt, eta}                               # {x} means {"x": x}
```

| Construct | Notes |
|---|---|
| `name = capability(arg=value)` | Arguments are always by name, never positional |
| `x = collection \| where(a == 1, b > 0)` | Several conditions combine with AND |
| `x = collection \| top(3, by=field)` | Sorts descending and truncates; `asc=true` inverts |
| `x = collection \| map({a, b: other})` | Projects fields |
| `x = collection \| map({g: cap(id=id)})` | **Calls a capability per item, in parallel** |
| `if` / `else` | The same name may be bound in both branches |
| `return {x, y}` | `{x}` is shorthand for `{"x": x}` |

On a collection you can read `.empty`, `.first` and `.count`. On a record, its fields
with a dot: `v.first.sku`.

Two rules that are easy to trip on:

- **Each name is bound once.** No reassignment — that is what makes the dependency
  graph exact.
- **No loops, no user functions, no imports, no arithmetic.** `map` over the pipe
  covers the collection cases.

### Statements run in parallel when they can

The compiler builds a dependency graph from which variables each statement reads.
In the example above, `oem` and `alt` do not depend on each other, so they execute
concurrently. A `map` that calls a capability fires one call per item, also
concurrent, capped at 16 in flight.

### Two predefined variables

| Variable | What it holds |
|---|---|
| `query` | The raw query text the agent received |
| `context` | The `context` dict passed to `POST /v1/agents/{name}/run`, with dot access |

`context` only arrives through the REST run endpoint. It is **not** propagated from
`spec.chain`, WebSocket, or channels — in those paths a program can only read
`query`.

For pulling fields out of free text there is `ask()`, which consults the model from
inside the program:

```glyph
id    = ask("Return only the order number, nothing else.", context=query)
order = find_order(order_id=id)
```

Each `ask` is a model round-trip the program chose to pay. An extraction like this
costs ~30 output tokens against the ~8,000 of writing a whole program.

## The authoring cycle

The model is the author, you are the reviewer, the runtime is the executor.

1. Run the agent **once** with `pattern: glyph` and no `program`, using a
   representative query.
2. The result carries `glyph.program` — the text the model wrote.
3. Review it and **parameterize whatever was hardcoded** from that query, typically
   identifiers, replacing them with `context.<field>`.
4. Paste it into `spec.program`. From then on the agent runs without the model.

## Configuration

```yaml
spec:
  orchestration:
    pattern: glyph
    narrate: true      # default. false returns the program result as JSON
    max_repairs: 2     # default. Ignored when spec.program is set
  program: |           # optional. When present, the model is never asked
    ...
```

**`narrate: false`** skips the second model call and returns the program's result as
JSON. It is the right choice for an agent that feeds another link in a chain: if
nobody is going to read the prose, writing it is a wasted call.

**`max_repairs`** caps the retries when the model writes a program that does not
compile. Each repair costs a full model call. It has no meaning with `spec.program`,
because a fixed program that does not compile stops the agent from loading.

## What fails, and when

| When | What happens |
|---|---|
| `spec.program` does not compile | **The agent does not load.** Deployment error with line and message, surfaced in `GET /v1/agents` under `error` |
| A capability fails at runtime | The agent returns an error with the partial state. It does **not** fall back to generating or to `react` |
| The program calls a tool the agent lacks permission for | It does not compile — the catalog is already permission-filtered |
| `spec.program` with a different `pattern` | The agent does not load |
| The `glyph` extra is missing, no `program` | Falls back to `react` with a warning |
| The `glyph` extra is missing, `program` present | **The agent does not load.** Silently degrading a fixed program to `react` would change the run's cost by two orders of magnitude |

Failing explicitly is deliberate. Falling back to generation would bring the cost
back exactly when least expected, and impossible to budget.

Programs are validated **when the agent loads**, not on the first query — a broken
program is a configuration error, and it should be a deployment failure rather than
an error in the first customer's face.

## When to use it

**Yes**, if your agent:

- Chains five or more tools where each result feeds the next
- Has independent branches that can run concurrently
- Applies a tool to every item in a list
- Feeds another agent rather than a person — pair it with `narrate: false`
- Does the same thing every time, so its program can be fixed in `spec.program`

**No**, if your agent:

- Resolves with one or two tools — the fixed cost of the grammar block dominates
- Needs to see the data before deciding what to do next
- Runs on a model with explicit reasoning, which spends enormous output writing code
- Is conversational — the fixed cost is paid on every turn

A fixed-program agent stops being conversational. That is a consequence of the
design, not a defect.

## Measuring your own case

Two tools ship with the repository. Start with the cheap one:

```bash
# Rate of valid programs on the first try — minutes and cents
BENCH_MODEL=... BENCH_ENDPOINT=... BENCH_API_KEY_ENV=... \
uv run python -m bench.glyph.validity

# Full benchmark: react vs glyph vs glyph without narration
uv run python -m bench.glyph.run
```

Validity is the metric that decides. A model below 50% pays repairs constantly, and
each repair is a full model call — no saving survives that. Models that write code
well without deliberating at length score 80%+; older or smaller models scored 38%.

## See also

- [Agent Chaining](/astromesh/configuration/agent-chaining/) — declarative chaining between agents
- [Agent YAML Schema](/astromesh/configuration/agent-yaml/) — the full spec
- [`docs/GLYPH_GUIDE.md`](https://github.com/monaccode/astromesh/blob/develop/docs/GLYPH_GUIDE.md) — the measured numbers, model recommendations, and how to optimize
