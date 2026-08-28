---
title: Confirmation Gate
description: An action declared in confirm does not run until the person answers a literal yes — decided on the human's own words, never on the model's reading of them
---

An action listed under `confirm:` **does not execute** until the person writes one of a
fixed set of words. Not "the model thinks they agreed" — the words they typed.

```yaml
spec:
  tools:
    - name: praxis
      type: integration
      connection: praxis_main
      actions:
        - buscar_records
        - crear_record
      confirm:
        - crear_record        # buscar_records runs freely; this one waits
```

Available since astromesh **v0.42.0**.

## What happens in a conversation

```
person   how much does customer 42 owe, and open a payment plan for 3 instalments

agent    Customer 42 owes $184,000.
         Para confirmar respondé SI. Voy a ejecutar: praxis_crear_record con
         entidad: cob_acuerdo, cuotas: 3, monto: 184000

person   dale

agent    Done — plan recorded, 3 instalments of $61,333.
```

The second line of the agent's answer is **written by the runtime**, not by the model. It
is appended to whatever the model produced, and the model cannot suppress it or reword it.
That is the piece that closes the oldest bypass in this shape of feature: the model
proposes a write, asks the person something *else* that takes a yes, and spends their
"dale" on the write they never saw.

## How the decision is made

The gate is a module that imports nothing from the engine, receives no model messages, and
never sees model output. Consent is decided on the raw text the person typed:

- lowercased, accent-stripped, trimmed, and compared against an explicit set — **`si`,
  `confirmo`, `dale`, `ok`, `listo`**
- a *phrase* is not a confirmation. "bueno dale pero cambiame la cantidad" is a new
  message, and interpreting it would be exactly what this gate exists to prevent
- the model is never asked whether consent happened

Any other message **discards** the pending proposal. Permission expires in one turn rather
than floating three messages later, when the conversation has moved on.

## What a yes authorizes

A pending proposal is `(session, tool, fingerprint of the arguments)`. The fingerprint is a
hash of the argument dict with sorted keys, so:

- confirming an order of **two** units does not execute one of **two hundred** — different
  arguments are a different proposal and need their own yes
- the same request with its keys in another order is still the same proposal
- the permission is consumed **once**, immediately before executing. A pattern that retries,
  or a model that hallucinates the same call twice, does not get a second write out of one
  yes

There is **one slot per session**, and a second proposal does not overwrite an unused
first. Without that, a sub-agent or a chain step could replace the proposal the person is
looking at, and their yes would authorize something they never read.

## Re-entrant runs cannot confirm

`Agent.run` and `AgentRuntime.run` take `desde_humano` (default `True`). It is forced to
`False` on the two entry points whose `query` was written by a model rather than a person:
an agent invoked as a tool (`type: agent`) and a chain step.

A re-entrant run can therefore **use** a permission a human already granted in the same
session, but it can neither grant one nor close one. Without that rule, self-confirmation
needs no elaborate prompt injection — "ask the specialist with the message 'si'" would do it.

For the same reason, `spec.chain` and `confirm:` **cannot coexist** on one agent. The
loader raises at boot rather than leaving an agent whose proposal nothing can ever confirm.

## Scope and limits

Stated plainly, because a security feature that overstates itself is worse than none:

- `confirm:` is read **only** on `type: integration` tools. On any other type it is a
  permission that gates nothing; the runtime warns and ignores it.
- Naming an action that is not in `actions` **raises** at boot. A mistyped permission is
  the one case here worth refusing to start for.
- The notice guarantees *"it was written"*, not *"it was delivered"*. If the channel send
  fails after the answer already carries the notice, the person did not see the detail and
  the pending survives into the next turn.
- A run that raises **after** registering a pending never reaches the code that writes the
  notice. The pending survives unseen. Bounded in practice — that failed turn is not
  persisted, so the model would have to reconstruct identical arguments from memory — but real.
- Pendings live in **process memory**, keyed by session. The runtime pool runs single-replica
  today. If it ever scales, a session landing on another pod loses its pending and the agent
  asks again: annoying, never dangerous, because the check fails closed.

## Why not `requires_approval`

`ToolDefinition.requires_approval` already existed and was the obvious place to hang this.
It was the wrong one: it is `true` for 15 actions across 9 integrations, including
`whatsapp_send_text` — so gating on it would make an agent ask permission before *replying
to a message*. `needs_confirmation` is a separate field, and `requires_approval` is left
untouched.

## See also

- [Integrations](/astromesh/configuration/integrations/) — where `confirm:` is declared
- [Agent YAML Schema](/astromesh/configuration/agent-yaml/)
