---
title: "In Astromesh: tools and ADK"
description: Call a remote A2A agent from an Astromesh agent — a type a2a tool in the agent YAML (core 0.74.0+) or remote_a2a() in the ADK (0.7.0) — with the same policy, untrusted output and agent origin as the library.
---

Two ways to call a remote A2A agent from Astromesh, both built on
[`astromesh-a2a`](/astromesh/a2a/library/):

| | Where | Install | Since |
|---|---|---|---|
| **`type: a2a` tool** | Agent YAML, run by the core runtime (and by Nexus' pool) | `pip install "astromesh[a2a]"` | core 0.74.0 |
| **`remote_a2a()`** | Python agents written with the ADK | `pip install "astromesh-adk[a2a]"` | ADK 0.7.0 |

Both keep the library's guarantees: only the host of `card_url` is reachable, the secret comes from
an environment variable, the remote's words reach the model wrapped as untrusted data, a remote's
question is never answered for the user, and every call is an **agent turn** (`Origin.AGENT`), so a
remote can never confirm a [`confirm`-gated](/astromesh/configuration/confirmation-gate/) action.
The key-by-key reference for the YAML tool lives in
[Multi-agent Composition](/astromesh/configuration/multi-agent/#calling-remote-a2a-agents), and the
ADK one in [Remote Execution](/astromesh/adk/remote-execution/#remote-a2a-agents); this page puts
both in one place and adds what happens around them.

## The `type: a2a` tool

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: assistant
spec:
  tools:
    - name: agenda_externa
      type: a2a
      card_url: https://agents.example.com/.well-known/agent-card.json
      auth: {api_key_env: AGENDA_KEY}        # or {bearer_env: AGENDA_TOKEN}; optional
      policy: {max_bytes: 262144, timeout: 30, accept_parts: [text, data]}   # optional
      description: "Company meeting scheduler"   # optional; built from the card if missing
```

### Keys

| Key | Required | Rules |
|---|---|---|
| `name` | yes | The tool name the model sees. Must not repeat another tool of the agent. |
| `type` | yes | `a2a` |
| `card_url` | yes | The remote's Agent Card URL, or its base URL (then `/.well-known/agent-card.json` is appended). **https** only unless `policy.allow_insecure_http: true`. Its host becomes the **only** entry of the policy's allowlist: the YAML cannot add others. |
| `auth` | no | An object with **exactly one** of `api_key_env` (sent as `X-API-Key`) or `bearer_env` (`Authorization: Bearer`). The value is the **name** of an environment variable (`^[A-Za-z_][A-Za-z0-9_]*$`), never the secret. |
| `policy.max_bytes` | no | Integer, 1 to 16 MiB (`16777216`). Default: the library's 1 MiB. |
| `policy.timeout` | no | Seconds, `> 0` and `≤ 600`. Default: the library's 60 s. It also sets the tool's own timeout (rounded up). |
| `policy.accept_parts` | no | Non-empty list of `text`, `data`, `file`. Default: `[text, data]`. |
| `policy.allow_insecure_http` | no | Boolean. Allows an `http://` card URL; local development only. |
| `description` | no | What the model reads. If missing, it is built from the card (see [Lifecycle](#lifecycle)). |
| `rate_limit`, `max_result_tokens` | no | Same as any other tool type. |

There is no `parameters` key: the tool always takes `{"query": string}` — "the message for the
remote agent: a request, or the user's own answer when the remote is waiting for input". The
[VS Code schema](/astromesh/reference/os/vscode-extension/) (`agent.schema.json`) enforces the same
rules, and Forge keeps a `type: a2a` tool intact when you edit an agent that has one.

**Validation is at load time and without network.** An unknown key (including inside `policy` or
`auth`), an `http` card without `allow_insecure_http`, a secret written in the YAML, or a limit out
of range is a `ValueError`; error messages name keys, never values, so a pasted secret does not end
up in the API's error list or the log. Without the extra, the agent stays in `draft` with "install
astromesh[a2a]" — at load, not on the first call.

### What the model gets back

The observation is `{answer, status, task_id?, pending?}`:

| Field | |
|---|---|
| `answer` | Everything the remote wrote, inside one escaped `<remote-agent-output untrusted="true" agent="…" status="…">` block. The remote's `data` parts go **inside** the block as `[data] {...}` lines; nothing remote is left raw outside it. A pending task adds the library's note after the block: only the user can answer. |
| `status` | `completed`, `input_required` or `auth_required` |
| `task_id` | The remote task, when there is one |
| `pending` | `true` when the remote has not finished |

**`input_required`, per session.** When the remote asks for something, the task id is remembered per
`(session_id, tool)`. The next call to that tool **in the same session** answers it with `reply()`
instead of starting a new task; another session starts its own. Without a session nothing is
remembered. The model's description tells it to ask the user and call again with the user's answer,
never to answer a confirmation itself — and since the call is an agent turn, a remote that is
"confirmed" by the model is still not a human confirmation anywhere.

**Errors are observations.** A remote that is down, a refused policy check or a failed task comes
back as `{"error": "Remote A2A agent error (<Class>): <short, escaped message>", "status": "failed"}`
and the run continues. If a `reply()` fails transiently (timeout, network), the task stays pending
for the session and the observation keeps `task_id` and `pending: true`; a `TaskFailed` releases it.

### Remote usage

A2A has no field for cost. The convention: a remote that wants to report its consumption sends a
`data` part whose **only** key is `usage`:

```json
{"usage": {"cost": 0.0042, "input_tokens": 812, "output_tokens": 164}}
```

That part is metadata, not answer: it is taken out of the untrusted block and recorded on the
tool's trace span as `a2a.usage_remoto` (up to 20 short keys with scalar values; non-finite numbers
are dropped). It is **not** added to `usage.by_model` or the run's totals, because it is not one of
your models.

**Nexus sends it.** Since Nexus 0.28.2, a `COMPLETED` A2A task carries `{"usage": {...}}` as the last
part of its answer artifact, so a `type: a2a` tool pointed at a Nexus-published agent records it with
no setup. The fields are scalars: `input_tokens`, `output_tokens`, `cached_tokens` (only if above 0),
`credits` and `credits_micros` (what the run was charged), `pricing_status` (`priced` or `unpriced`),
`model` (the one with most tokens) and `models` (how many, only if more than one). It is only on runs
that closed ok: `failed`, `canceled` and `rejected` tasks charge nothing and have no usage part.
`credits` are Nexus credits, not money, so the ADK's `RunResult.cost` stays `0` for a Nexus remote
and the whole part lands in the core tool's trace span as `a2a.usage_remoto`.

### Trace span

The tool's span carries `a2a.card_url`, `a2a.status`, `a2a.task_id`, `a2a.reply_to` (when the call
answered a pending task), `a2a.error` (the error class), `a2a.usage_remoto` and `a2a.trace` (the
library's redacted per-stage trace, first 50 entries).

### Lifecycle

- **One client per tool.** The `RemoteAgent` is created lazily inside the running event loop and
  recreated if the loop changes (the library binds a client to its loop).
- **Description from the card.** A tool without `description` starts with a generic one; before a
  run reads the tool schemas, the runtime fetches the card (waiting at most 5 s) and builds the
  description from it, quoting the remote's text as untrusted under Astromesh's own framing. A
  remote that is down keeps the generic description and is retried at most every 5 minutes.
- **Closing.** `AgentRuntime.aclose()` closes the clients when the API shuts down. A `reload` or
  `deploy` that replaces the agent, or pausing or removing it, closes the old agent's clients after
  a grace period equal to its longest `policy.timeout`, so a call in flight can finish.
- **Nexus.** Nexus' runtime pool runs core 0.74.1 and its image ships the `a2a` extra (Nexus
  0.28.2), so a published agent can declare `type: a2a` tools.

## ADK: `remote_a2a()`

```python
from astromesh_adk import agent, remote_a2a

agenda = remote_a2a(
    "https://agents.example.com/.well-known/agent-card.json",
    api_key_env="AGENDA_KEY",   # optional: the variable's NAME, sent as X-API-Key
    policy={"timeout": 30},     # optional: max_bytes, timeout, accept_parts, allow_insecure_http
    name="agenda",              # optional: the tool name (default: from the host)
    description=None,           # optional: replaces the generic description
)

result = await agenda.run("Book me on Tuesday", session_id="s1")
print(result.answer, result.metadata["status"])

@agent(name="assistant", model="openai/gpt-4o", tools=[agenda.as_tool()])
async def assistant(ctx):
    """Help the user; use the agenda for appointments."""

await agenda.aclose()  # or: async with remote_a2a(...) as agenda:
```

`remote_a2a(card_url, *, api_key_env=None, policy=None, name=None, description=None)` returns an
object with the shape of an ADK agent:

| Use | What you get |
|---|---|
| `await run(query, session_id=…)` | A `RunResult`: `answer` is the remote's text; `metadata` has `status`, `task_id`, `context_id`, `pending`, `data`, `usage_remoto` and `a2a_trace`. `cost` is `0` unless the remote reports `{"usage": {...}}`. Errors raise `RemoteError` (`RemoteUnavailableError` when the egress guard blocks the destination). |
| `stream(query, session_id=…)` | `token` events with the remote's text and a final `done`. A session with a pending task is answered with `reply()` (A2A streams only start new messages), as one `token` plus `done`. |
| `as_tool()` | A tool for another ADK agent. The model sees `{answer, status, task_id?, pending?}` with the remote's words (its `data` included) inside the untrusted block; a failure is an `{error, status: "failed"}` observation. The remote's usage goes to the tool span (`a2a.usage_remoto`), not to the parent's cost. |

Same rules as the YAML tool: checked at construction without network (without the extra,
`MissingA2AExtraError`, an `ImportError`), only the `card_url` host allowed, `http` refused unless
`policy={"allow_insecure_http": True}`, and **always `Origin.AGENT`** — including a direct `run()`,
because the ADK cannot tell whether a person typed the query. Credentials: `api_key_env` only (sent
as `X-API-Key`).

**Pending tasks and concurrency.** An `input_required` is kept per `session_id` (as a tool, per
parent session), and the next call in that session answers it. With concurrent calls in the same
session, the first one takes the pending task and resumes it; the others start new tasks.

The ADK's other remote paths (`bind()`, `connect()`, `remote()`, against an Astromesh node rather
than an A2A server) also declare `origen: "agente"` since ADK 0.7.0. See
[Remote Execution](/astromesh/adk/remote-execution/).

## Which one, and when to use `type: agent`

| You want to call… | Use |
|---|---|
| Another agent in the same runtime | [`type: agent`](/astromesh/configuration/multi-agent/) — in process, shares the trace, its usage is added to the parent's |
| An agent on another runtime or framework that speaks A2A | `type: a2a` (YAML) or `remote_a2a()` (ADK) |
| An agent published in Nexus | Either of the above, pointed at its [Nexus Agent Card](/astromesh/nexus/a2a-server/) with the tenant's API key (`api_key_env`) |
| A remote agent from LangChain, CrewAI, smolagents… | [`RemoteAgent.as_tool(...)`](/astromesh/a2a/library/#framework-tools) |
