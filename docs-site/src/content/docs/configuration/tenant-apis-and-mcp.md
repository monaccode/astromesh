---
title: Tenant APIs & MCP Servers
description: Tool types api and mcp — a tenant's own API or MCP server declared inline in the agent manifest, read-only by default, public hosts only, and writes that are proposed instead of executed
---

An [integration](/astromesh/configuration/integrations/) is a manifest from the catalog,
written by whoever maintains the runtime. `type: api` and `type: mcp` are the other case:
the tenant's **own** API or MCP server, described by the tenant's admin (a control plane
such as CLARUS emits it) and carried **inline** in the agent manifest.

```yaml
spec:
  tools:
    - name: erp-cliente          # kebab slug
      type: api
      connection: erp_main       # base_url + credential, per run
      auth: { scheme: bearer }
      operations:
        - name: buscar_cliente
          description: Find a customer by tax id.
          writes: false
          parameters:
            cuit: { type: string, description: The customer's tax id., required: true }
          request:
            method: GET
            path: /clientes
            query: { cuit: "{cuit}" }
```

The model sees `erp_cliente_buscar_cliente`.

`type: api` available since astromesh **v0.57.0**, `type: mcp` since **v0.58.0**,
`mode: propose` since **v0.59.0**.

## A bad declaration does not load the agent

This is the opposite of `integration`, which warns and skips. The declaration is written by
a tenant, and an API the admin believes is enabled but silently isn't is the same failure
that `confirm:` already cost once. So every rule on this page **raises** when the agent is
built: an invalid spec, a write without `mode: propose`, a name collision, a name over 64
characters, a missing `mcp` extra.

## Tool `type: api`

Each operation becomes one tool named `<slug with _>_<operation>`, executed by the same
declarative executor as the catalog (path, query and body interpolation, `response.select`).

| Key | Required | What it does |
|-----|----------|--------------|
| `name` | Yes | Kebab-case slug (`erp-cliente`). |
| `connection` | Yes | The connection that supplies `base_url` and the credential under the key `credential`. |
| `auth.scheme` | Yes | `header`, `bearer`, `basic` or `query`. `header` names the header in `auth.header`, `query` the parameter in `auth.param`. For `basic`, `credential` is a mapping with `username` and `password`. |
| `operations` | Yes | Non-empty list. Each takes `name` (snake_case), `description`, `parameters`, `request`, `response` — the same shapes as a [catalog action](/astromesh/configuration/integrations/#writing-a-manifest). |
| `description` | No | Description of the API. |
| `rate_limit` | No | Applies to every operation. |

Rules per operation:

- **Read-only unless it proposes.** `writes: false` (exactly — `writes: 0` is not false), or
  `writes: true` with `mode: propose`. Anything else, including `mode` on a read, raises.
- `request.method` is `GET` or `POST`.
- `request.path` must start with `/`. The executor builds `base_url + path`, and without the
  slash `@other.com/x` would send the call — and the credential — to another host.
- `request.headers` is rejected: authentication goes through `auth`, never around it.
- There is no `base_url` in the spec. It comes from the connection.

### Public hosts only

An `api` tool runs with `permitir_internos=False`. The destination must be public: a private
IP, `localhost`, a name without a dot, `*.svc`, `*.cluster.local`, `*.local`, `*.internal`,
or a name that resolves to any non-global address comes back as a tool error.

The check is not a separate step that DNS can race. The host is resolved **once**, **every**
returned address must be global, and the connection is pinned to that IP — `Host` and TLS
SNI keep the original name, so the certificate is still verified against it. A tenant
controls the DNS of its own `base_url`; with a low TTL it could answer differently between
the check and the connect. A name that fails to resolve is blocked too, rather than falling
back to an unpinned request.

NAT64 addresses (`64:ff9b::/96`) are judged by the IPv4 inside them (since **v0.58.0**):
`64:ff9b::a00:5` is `10.0.0.5` and is blocked; `64:ff9b::808:808` (what DNS64 returns for a
public IPv4-only host) passes.

A response that is not text — a non-text `content-type`, or no `content-type` and a body that
is not UTF-8 — or that exceeds 5 MB comes back as a tool error. JSON over the cap is an error,
not a truncation: truncated JSON is no longer JSON.

## Tool `type: mcp`

The tenant's MCP server, with a **snapshot** of its tools inline. The runtime does not
discover: the control plane listed the server's tools when the admin registered it, and the
agent is built from that list with no network and no credential (the credential only
arrives per run).

```yaml
spec:
  tools:
    - name: soporte
      type: mcp
      connection: soporte_mcp
      path: /mcp
      auth: { scheme: header, header: X-Api-Key }
      tools:
        - name: buscar_ticket
          description: Find a support ticket by number.
          writes: false
          input_schema:
            type: object
            properties: { numero: { type: string } }
            required: [numero]
```

The model sees `soporte_buscar_ticket` — the slug with `_`, then the tool name lowercased with
anything outside `[a-z0-9_]` replaced by `_`.

| Key | Required | What it does |
|-----|----------|--------------|
| `name` | Yes | Kebab-case slug, at most 30 characters. |
| `connection` | Yes | `base_url` and `credential`. The call goes to `base_url + path`. |
| `path` | Yes | Starts with `/`, no query or fragment. |
| `auth.scheme` | Yes | `bearer`, or `header` with `auth.header`. A reserved header (`Host`, `Content-Type`, `Accept`, `Mcp-Session-Id`, …) is rejected. |
| `tools` | Yes | At least one. Each has `name`, `description`, `input_schema`, `writes`, and optionally `mode`. |
| `rate_limit` | No | Applies to every tool of the server. |

Unknown keys are rejected. Per tool:

- `writes` has **no default**: an entry that does not declare it does not validate. `true`
  only with `mode: propose`.
- `input_schema` must be `type: object`, at most 16 KB serialized and 8 levels deep.
- Two tools that normalize to the same name raise.
- The runtime needs the `mcp` extra (`pip install "astromesh[mcp]"`, which pins
  `mcp>=1.28.1,<2`). Without it the agent does not load — otherwise it would load green and
  every call would fail.

### Each call is a short session

`initialize` + `tools/call` + close, with the official SDK over `TransportePineado` — the
same guard as `api` tools, as an httpx transport: one resolution per host, all addresses
global, IP pinned with the original `Host` and SNI, `Accept-Encoding: identity` (any other
`content-encoding` is rejected, so the 5 MB cap counts decoded bytes), and no redirects.
The 30 s timeout covers the whole call, not each request.

A call **never raises**. `isError`, a JSON-RPC error, a blocked host, a 3xx, a 4xx/5xx
("el servidor MCP contestó 401", without the pinned IP), a timeout, an oversized body or an
incompatible SDK all come back as the tool's error, and the run continues.

## Name collisions

An `api` or `mcp` tool whose final name matches **any** other tool of the agent — builtin,
integration, another `api` or `mcp` — does not load, whichever is declared first. A final
pass catches a tool declared *after* it, which would otherwise overwrite it silently. For a
tool that proposes, being overwritten would turn a proposal into a real call.

## `mode: propose` — writes that wait for approval

An `api` operation or `mcp` tool with `writes: true` and `mode: propose` is registered with
the same name and schema as a read, but its handler **calls nobody**. It validates the
arguments against the schema (`type` — also as a list —, `properties`, `required`, `enum`,
`items`), records them on the run, and tells the model the write was left for approval and
was **not** executed.

The caller receives them in `propuestas` — on the `POST /v1/agents/{name}/run` response and on
the WebSocket `done` event — and executes whatever a person approves:

```json
"propuestas": [
  {
    "tool": "erp_cliente_crear_pedido",
    "tipo": "api",
    "destino": "erp-cliente",
    "operacion": "crear_pedido",
    "argumentos": { "cliente": "30-12345678-9", "items": [ … ] }
  }
]
```

`propuestas` is always present, empty when nothing was proposed. Limits: 20 proposals per
run (sub-agents included), arguments at most 16 KB per proposal. A validation failure goes back to the model as a tool error and
never fails the run — that would lose the proposals already recorded.

### Sub-agents propose on their caller's list

Since **v0.61.0**, an agent invoked as a tool (`type: agent`) proposes on the list of the run
that called it. What the child proposes comes out in the **parent's** `propuestas`, with
`via` set to the child's `metadata.name` (the parent's own proposals carry no `via`):

```json
{ "tool": "erp_cliente_crear_pedido", "via": "especialista-pedidos", "argumentos": { … } }
```

The child's own answer does not repeat them, and the 20-proposal cap is shared by the whole
run, grandchildren included. If a sub-agent fails **after** proposing, its proposals stay on
the parent's list, and a retry can propose them again — every proposal is approved by a
person, and `via` shows where it came from. Before v0.61.0 these runs refused the proposal.

### Where a proposal is refused

Where a proposal could not reach anyone, it is **refused to the model** instead of being lost:

- **Re-entrant runs without a caller's list** — a workflow or `spec.chain` step, a call
  through astromesh's own MCP server. Their answer is not the `/run` response.
- **Channel routes that do not return `propuestas`** — WhatsApp and agent channels. The model
  is told this channel does not accept writes with approval.

### Relation to the Confirmation Gate

Both stop a write until a person agrees; they differ in who holds the write.

| | [`confirm:`](/astromesh/configuration/confirmation-gate/) | `mode: propose` |
|---|---|---|
| Declared on | `type: integration` actions | `type: api` operations, `type: mcp` tools |
| Who approves | The person, in the same conversation, with a literal yes | Whoever invoked the run, outside it |
| Who executes | The runtime, on the next turn | The caller — the runtime never does |

`confirm:` is not read on `api` or `mcp` tools.

## See also

- [Integrations](/astromesh/configuration/integrations/) — the catalog, connections, and the
  executor these tools reuse
- [Confirmation Gate](/astromesh/configuration/confirmation-gate/)
- [Tool Registry](/astromesh/reference/core/tool-registry/)
