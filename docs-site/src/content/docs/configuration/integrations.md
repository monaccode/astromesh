---
title: Integrations
description: Turn an integration.yaml manifest into agent tools — the shipped catalog, the connection that carries the credential, and how to write your own
---

An **integration** is a YAML manifest that becomes agent tools. No Python, no plugin, no
runtime code: the manifest declares the HTTP requests, and the runtime's declarative
executor performs them.

```yaml
spec:
  tools:
    - name: google_sheets       # the integration slug, from the catalog
      type: integration
      connection: sheets_main   # which credential to sign the request with
      actions:                  # allowlist — required
        - get_values
        - append_values
```

That agent sees two tools, named `google_sheets_get_values` and
`google_sheets_append_values`. The tool name the model calls is always
`<slug>_<action>`.

Available since astromesh **v0.37.0**.

## Why a manifest instead of a tool

A built-in tool is Python that ships in the runtime, so adding one means a release. An
integration is a file. The manifest carries the shape of the API — paths, methods, auth
scheme, pagination — and the **connection** carries the credential, which is per tenant
and never lives in the manifest. One file therefore serves every customer.

That split is what makes a manifest safe to commit. It is also why most manifests declare
no `base_url`: for an API each customer self-hosts, the URL comes from the connection.
A default there would quietly hit the wrong server.

## The catalog

Manifests are auto-discovered from `astromesh/integrations/catalog/`. What ships today:

| Slug | Actions | What it reaches |
|------|---------|-----------------|
| `http` | `get`, `post`, `put`, `delete` | Any internal API. `base_url` and auth come from the connection. |
| `whatsapp` | `send_text`, `send_template`, `get_media` | Meta Graph API. |
| `gmail` | `list_messages`, `get_message`, `list_labels`, `send_message` | Gmail API. Sending builds RFC 5322 MIME in a handler. |
| `google_drive` | `list_files`, `get_file`, `search`, `upload_file` | Drive v3, with resumable upload. |
| `google_sheets` | `get_spreadsheet`, `get_values`, `update_values`, `append_values` | Sheets v4. Entirely declarative. |
| `facebook` | `list_page_posts`, `get_post`, `list_comments`, `create_post` | Page feed and comments. |
| `instagram` | `list_media`, `get_media`, `list_comments`, `publish_photo`, `publish_container` | Publishing chains container + publish in one handler. |
| `tiktok` | `get_user_info`, `list_videos`, `publish_video`, `get_publish_status` | Paginates over POST bodies (`cursor_in: body`). |
| `praxis` | `buscar_records`, `obtener_record`, `crear_record`, `actualizar_record` | Generic CRUD over any entity of the PRAXIS ERP. `obtener_record` reads one row by id — `buscar_records` cannot, because its filter resolves against *declared* fields and `id` is a system column, so `id:eq:<uuid>` comes back `422`. |
| `praxis_cobranzas` | `simular_planes`, `registrar_acuerdo` | Debt-collection vertical: offer payment plans, record the agreement. |
| `praxis_mecanicos` | `saldo_cliente`, `disponibilidad` | Workshop vertical: what a customer owes, and free slots in the calendar. |
| `praxis_inmobiliaria` | `informar_pago` | Rentals vertical: record a payment a tenant reports, in one idempotent call. |
| `praxis_alcaldia` | `mi_cuenta`, `consultar_clasificador`, `informar_pago` | Municipal-revenue vertical. `mi_cuenta` takes **no parameters** on purpose: the taxpayer's identity comes from the channel, never from the conversation, so there is no way to ask for somebody else's account. |

The `praxis_*` manifests are deliberately separate from `praxis`: the generic one serves
any customer, the verticals name a domain. They share the same connection.

Read the catalog at runtime:

```bash
curl localhost:8000/v1/integrations              # slugs, auth scheme, action counts
curl localhost:8000/v1/integrations/google_sheets # + every action and its parameters
```

Neither endpoint returns credential **values** — only which credential material a
connection has to supply. That is what a control plane reads to draw its connections UI.

## Declaring one in an agent

```yaml
spec:
  tools:
    - name: praxis
      type: integration
      connection: praxis_main
      actions:
        - buscar_records
        - crear_record
      confirm:                  # subset of actions — see Confirmation Gate
        - crear_record
      rate_limit:               # optional; overrides the manifest's
        requests_per_minute: 30
```

| Key | Required | What it does |
|-----|----------|--------------|
| `name` | Yes | The integration slug. Not a tool name — one entry registers several tools. |
| `type` | Yes | `integration`. |
| `connection` | Yes | Name of the connection whose credential signs the request. |
| `actions` | Yes | Allowlist. Exposing every action of several integrations inflates the prompt and makes the model choose worse. |
| `confirm` | No | Actions that need a human "yes" before they run. See [Confirmation Gate](/astromesh/configuration/confirmation-gate/). |
| `rate_limit` | No | Per-agent override of the action's or the manifest's limit. |

`description` is **not** read here. An integration tool describes itself from the
manifest, which is the copy the model actually sees; a `description` in the agent YAML
goes nowhere. The runtime warns about it — see [When it silently does nothing](#when-it-silently-does-nothing).

## Connections

A connection is a named bag of credential material. The runtime **never stores, encrypts
or refreshes it** — it resolves it, in this order:

1. **The run bundle.** A control plane (Nexus) injects `connections` into the run. Highest
   priority.
2. **`config/connections.yaml`**, with `${VAR}` expanded from the environment. This is the
   self-hosted path.
3. **Absent.** The action returns `credential_missing`. The run does not crash.

```yaml
# config/connections.yaml  (gitignored — copy from connections.yaml.example)
connections:
  wa_main:
    access_token: "${WHATSAPP_ACCESS_TOKEN}"

  # `http` and the PRAXIS manifests take base_url from the connection, not the manifest.
  praxis_main:
    api_key: "${PRAXIS_API_KEY}"
    base_url: "${PRAXIS_BASE_URL}"
```

`base_url` is the one reserved key: it is lifted out of the material and used as the
request base. Everything else is credential material, matched against the manifest's
`auth.credential`.

Over HTTP, a caller supplies the bundle per run:

```json
POST /v1/agents/collections/run
{
  "query": "how much does customer 42 owe?",
  "connections": { "praxis_main": { "api_key": "…", "base_url": "https://…" } }
}
```

The bundle travels through the closure, never through the tool arguments — arguments are
written to the trace, and a credential there would end up on disk.

## Writing a manifest

```yaml
apiVersion: astromesh/v1
kind: Integration
metadata:
  name: crm                    # the slug
  version: 0.1.0
  description: What this reaches, in one paragraph.
spec:
  base_url: https://api.example.com   # omit when the tenant supplies it
  auth:
    scheme: bearer                     # bearer | header | query | basic | none
    credential: api_key                # which key of the connection material to use
  defaults:
    timeout_seconds: 30
    headers: {}
  actions:
    - name: find_contact
      description: >
        What this does and when to call it. This is the only text the model reads
        to decide, so write it for the model, not for a changelog.
      writes: false
      parameters:
        email:
          type: string
          description: The contact's email address.
          required: true
      request:
        method: GET
        path: "/contacts"
        query:
          email: "{email}"
      response:
        select: data            # dotted path into the body; omit to return all of it
      pagination:
        style: cursor           # cursor | offset
        cursor_path: meta.next
        cursor_in: query        # query (default) | body — POST searches need `body`
```

Rules worth knowing before you write one:

- **An action declares `request` or `handler`, never both and never neither.** `handler:
  python:module:function` is the escape hatch for the few APIs that cannot be expressed
  declaratively (Gmail's MIME encoding, Instagram's two-step publish).
- **`{param}` interpolation is restricted** and guarded against path traversal. It
  substitutes declared parameters, nothing else.
- **An optional parameter with no argument is omitted**, not sent as `null`. This matters:
  a null `capacidad_pago` reads as *zero capacity* on the other side, and the agent then
  says "I have nothing to offer you" because the person simply did not say a number.
- **`writes` is tri-state** — `true`, `false`, or undeclared. Reading over POST is
  legitimate and common (body searches, GraphQL), so an action with a mutating method must
  say which it is rather than being forced to lie. Consumers read `ActionSpec.mutates`,
  which collapses undeclared to `false`.
- **`description` cannot be empty.** It is the only thing the model reads.
- Unknown keys are rejected at load time. A misspelled field fails the manifest with a
  readable message instead of being ignored.

## When it silently does nothing

Every one of these was a real production failure before it became a warning. A misdeclared
integration does not stop the pod from starting — so it has to be visible in the log:

| Situation | What the runtime does |
|-----------|-----------------------|
| The slug is not in the catalog | Warns and skips the whole entry. The agent runs **without those tools** while its prompt still tells it to use them. |
| No `connection` | Warns and skips the entry. |
| No `actions` | Warns and skips the entry — the allowlist is mandatory. |
| An action name that the manifest does not have | Warns and skips **only that action**. |
| A key this runtime does not read (`type`, `name`, `confirm`, `connection`, `actions`, `rate_limit` are the ones it does) | Warns, naming the agent, the tool and the ignored keys. Usually means the manifest is newer than the runtime. |
| `confirm` on a tool that is not `type: integration` | Warns — that tool would never gate. |
| `confirm` naming an action outside `actions` | **Raises.** A mistyped permission is the one case worth refusing to boot for. |

If an agent is ignoring a tool it should have, `grep` the pod log for the agent's name
before reading its YAML again.

## Observability

Each call emits an `integration.call` span carrying the slug, the action, the HTTP status
and an `error_kind` — the classified failure (`credential_missing`, `rate_limited`,
`upstream_error`, …) that a control plane can act on without parsing a message.

## See also

- [Confirmation Gate](/astromesh/configuration/confirmation-gate/) — how `confirm:` stops a
  write until a person says yes
- [Agent YAML Schema](/astromesh/configuration/agent-yaml/) — the other tool types
- [API Endpoints](/astromesh/reference/api-endpoints/) — `/v1/integrations`
