# Guardrails que se aplican: `spec.guardrails` deja de ser decorativo

**Fecha:** 2026-10-13
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Release objetivo:** core 0.70.0 (minor: cambia el contrato del resultado de `run`).

## Problema

`spec.guardrails` se parsea y no se aplica. `AgentRuntime._build_agent`
(`runtime/engine.py:1263`) pasa el dict crudo a `Agent`, que lo guarda en
`self._guardrails` y nunca lo lee; `GuardrailsEngine` (`core/guardrails.py`) no se
instancia en ningún lado. Quien declaró `pii_detection: redact` cree que los emails no
llegan al modelo y llegan.

Además el motor, si se usara, tiene tres defectos:

- **Las claves no coinciden con los docs.** `architecture/agent-pipeline.md` documenta
  `forbidden_topics`, `max_characters`, `forbidden_keywords`; el código lee
  `blocked_topics`, `max_chars`, `blocked_patterns`. Templates usan `blocked_categories`
  y `allowed_topics`, que nada implementa.
- **`cost_limit` no limita costo:** recorta el texto de la respuesta a
  `max_tokens_per_turn / 1.3` palabras y agrega `... [truncated]`.
- **Bloquear es un `raise ValueError`**, que llega al llamador como error 500.

## Decisiones tomadas

1. **Activar para todos y sanear.** El motor corre para todo agente que declare reglas;
   las reglas rotas se corrigen en el mismo release y los manifiestos del repo se revisan
   uno por uno. No hay flag opt-in.
2. **Un bloqueo es una respuesta de rechazo, no un error.** La corrida termina bien,
   `answer` es un mensaje fijo, `blocked: true`.
3. **El stream se filtra.** Las reglas de salida se aplican a cada evento `token`.
4. **`cost_limit` es un presupuesto real de tokens de la corrida**, medido con el `usage`
   del proveedor y chequeado antes de cada llamada al modelo.
5. **Se aplica en `Agent.run`**, no como middleware de la API: cubre REST, WebSocket, SSE
   de `agent_channels`, WhatsApp, sub-agentes (`type: agent`) y pasos de chain. Cada
   agente aplica sus propias reglas; un sub-agente no hereda las del padre.

## Reglas soportadas

Cada regla es `{type, action?, message?, ...}`. `message` es el texto de rechazo si la
regla bloquea; default `"I can't help with that request."`.

| `type` | Dónde | Claves | `action` (default primero) |
|---|---|---|---|
| `pii_detection` | input, output | — | `redact`, `block`, `warn` |
| `topic_filter` | input | `blocked_topics` (alias `forbidden_topics`) | `warn`, `block` |
| `max_length` | input | `max_chars` (alias `max_characters`), default 10000 | `truncate`, `block` |
| `content_filter` | output | `blocked_patterns` (regex), `forbidden_keywords` (literales, alias que se escapan a regex) | `redact`, `block` |
| `cost_limit` | input u output (es de la corrida; da igual dónde se declare) | `max_tokens_per_turn` (obligatorio), `count: output \| total` (default `output`) | siempre bloquea |

- `pii_detection` mantiene los patrones y etiquetas actuales (`[REDACTED_EMAIL]`,
  `[REDACTED_PHONE]`, `[REDACTED_SSN]`, `[REDACTED_CC]`) y la ruta nativa
  (`RustPiiRedactor`). `warn` deja el texto y registra la detección en la traza.
- `topic_filter` mantiene la coincidencia por subcadena sin distinguir mayúsculas; la ruta
  Python usa `casefold()`. Sigue usando `RustTopicFilter` cuando está.
- `content_filter` con `redact` reemplaza cada coincidencia por `[FILTERED]` (como hoy).
- `topic_filter` en `output` no existe: se ignora con warning (ver abajo).

### Validación al cargar

`GuardrailsEngine(config, agent_name)` normaliza y valida una vez, en el bootstrap del
agente. Nunca impide que un agente cargue: lo inválido se descarta con un `logger.warning`
que nombra agente, dirección, índice y motivo.

- Tipo desconocido, o tipo en una dirección donde no aplica → regla descartada.
- Clave desconocida en una regla → warning, la regla sigue con lo que entendió.
  `blocked_categories` y `allowed_topics` caen acá con un mensaje específico: "requiere
  un clasificador; no soportado, use blocked_patterns / el system prompt".
- `action` desconocida → regla descartada.
- Regex inválida en `blocked_patterns` → ese patrón descartado.
- `cost_limit` sin `max_tokens_per_turn` entero positivo → descartada. Dos `cost_limit`
  → gana el menor.

El ADK (`astromesh-adk/astromesh_adk/guardrails.py`) declara defaults distintos
(`topic_filter: block`, `max_length: block`) al normalizar strings: no se toca; produce
dicts con `action` explícita que el core respeta.

## Flujo en `Agent.run`

### Entrada

Corre primero, sobre `query_text` (para un `query` multimodal, sobre cada parte `text`
por separado, reconstruyendo la lista con las partes redactadas). Las reglas corren en
el orden declarado; cada una ve el texto que dejó la anterior.

Todo lo de después usa el texto resultante: memoria (`build_context`), RAG, el atributo
`query` del span raíz, el patrón y el turno de usuario persistido.
`_PENDIENTES.habilitar` sigue leyendo el texto crudo: es un chequeo de consentimiento
que no viaja al modelo.

Si una regla bloquea: no hay memoria, RAG, prefetch ni llamada al modelo; se devuelve el
resultado de rechazo (abajo).

### Salida

Corre sobre `result["answer"]` justo después de `pattern.execute`, **antes** de:
el aviso de confirmación pendiente (texto del runtime, se agrega después), la
persistencia del turno y `build_data` (que parsea la respuesta ya filtrada, así `data`
no filtra lo que `answer` tapa).

Si una regla de salida bloquea: `answer` pasa a ser el mensaje, `blocked: true`, y
`data` queda `None` con `data_error` `"blocked by guardrail"`.

### Stream

`model_fn` emite `{"type": "token", "content": response.content}` con la respuesta
completa de cada llamada al modelo (no deltas). Con reglas de salida, ese `content`
pasa por las mismas reglas antes de emitirse; si una bloquea, el evento no se emite.
`cost_limit` no aplica acá.

### `cost_limit`

Un contador por corrida en la clausura de `run`. Cada respuesta de `model_fn` suma
`usage.output_tokens` (o `input_tokens + output_tokens` con `count: total`; una respuesta
sin `usage` suma 0). Al entrar a `model_fn`, si el contador ya es `>=
max_tokens_per_turn`, levanta `GuardrailBlocked`; `run` la atrapa alrededor de
`pattern.execute` y devuelve el rechazo. La llamada que cruza el límite se completa: el
presupuesto se chequea antes de gastar, no corta una respuesta a medias.

`GuardrailBlocked(direction, rule, reason, message)` es una excepción nueva en
`core/guardrails.py`. Un patrón puede tragarla o envolverla (Glyph convierte los errores
de una capacidad en `GlyphExecutionError` y reintenta): por eso `run` guarda el corte en
la clausura y, si `pattern.execute` vuelve o levanta otra cosa después de un corte,
devuelve igual el rechazo. Una vez cortado, toda llamada siguiente a `model_fn` vuelve a
levantar.

### Resultado de rechazo

```python
{
    "answer": "<message de la regla>",
    "steps": [],             # [] — un bloqueo nunca devuelve el contenido bloqueado
    "blocked": True,
    "guardrail": {"direction": "input" | "output" | "run", "rule": "<type>", "reason": "<texto>"},
    "propuestas": [...],     # como hoy
    "trace": {...},
}
```

`reason` describe sin repetir el contenido bloqueado (p. ej. `"blocked topic"`,
`"pii detected"`, `"pattern matched"`, `"token budget 4000 exceeded (4120)"`).

Toda corrida no bloqueada devuelve `blocked: False` y `guardrail: None`.

**Persistencia:** una corrida bloqueada en la entrada no persiste ningún turno (el texto
bloqueado no entra al historial). Una bloqueada en la salida o por `cost_limit` persiste
el turno de usuario (ya filtrado en entrada) y como respuesta el mensaje de rechazo.

**Confirmaciones pendientes:** si la corrida bloqueada había registrado una propuesta
sin confirmar (`needs_confirmation`), se descarta (`_PENDIENTES.cerrar`): la respuesta que
la explicaba fue reemplazada por el rechazo, y un "sí" en el turno siguiente no puede
autorizar algo que la persona no vio.

**API:** `AgentRunResponse` (`api/routes/agents.py`) gana `blocked: bool = False` y
`guardrail: dict | None = None`. El `done` del WebSocket también los lleva. El resto de
los llamadores (WhatsApp, `agent_channels`, chain) usan `answer`, que ya es el mensaje.

## Observabilidad

Spans `guardrails.input` y `guardrails.output` (sólo si hay reglas en esa dirección),
hijos del raíz, con atributos `rules` (los `type` aplicados), `redactions` (cantidad),
`warnings` (cantidad) y, si bloqueó, `blocked_by` y `reason`. Nunca el texto. Si bloqueó,
el span raíz lleva `guardrail.blocked: true`. `cost_limit` agrega
`guardrail.tokens_counted` al raíz.

## Manifiestos del repo

Se revisan los 4 agentes de `config/agents/` y los 15 templates de `config/templates/`
que declaran guardrails, con estos criterios:

- `cost_limit` pasa a contar salida de toda la corrida: los valores actuales (500–1500,
  pensados como largo de una respuesta) se reemplazan por `4000` salvo que el agente sea
  de una sola llamada sin tools.
- `content_filter.blocked_categories` → `forbidden_keywords` con términos concretos, o se
  elimina si el system prompt ya cubre la conducta.
- `topic_filter.allowed_topics` en output (brand-chef, nutritionist) → se elimina; el
  alcance ya está en el system prompt.
- `pii_detection` de entrada en agentes cuyas tools necesitan datos de contacto del
  usuario (agendar, cobrar, devolver): se revisa leyendo las tools de cada uno; si la
  redacción rompería la tarea se quita y se deja `pii_detection` de salida.
- `vscode-extension/schemas/agent.schema.json` (`$defs.guardrailRule`) refleja la tabla
  de reglas.

## Documentación

- `architecture/agent-pipeline.md` pasos 3 y 10 y `architecture/four-layer-design.md`
  (Guardrails Engine) reescritos con las claves, acciones y defaults reales, el resultado
  de rechazo y el filtro del stream.
- Changelog `[Unreleased]` → 0.70.0.
- Se documentan los límites: patrones PII con formato de EE. UU. (un teléfono argentino
  no se detecta), coincidencia de temas por subcadena, sin clasificadores.

## Tests

- `tests/test_guardrails.py` se actualiza: `topic_filter: block` ya no levanta
  `ValueError`; el motor devuelve un resultado estructurado. `cost_limit` deja de truncar.
- Motor: cada regla y acción, alias, validación (cada caso de "Validación al cargar"
  da warning y no rompe), orden de reglas, multimodal, ruta nativa y Python iguales en
  los casos ASCII.
- `Agent.run` con proveedor falso:
  - entrada redactada → el modelo, la memoria y la traza ven `[REDACTED_EMAIL]`;
  - entrada bloqueada → cero llamadas al modelo, `blocked: true`, nada persistido;
  - salida redactada → `answer`, memoria, `data` y los eventos `token` sin el email;
  - salida bloqueada → mensaje, `data` `None`;
  - `cost_limit` → corta antes de la llamada N+1 en un ReAct con tools; `count: total`;
  - sub-agente con sus propias reglas;
  - agente sin guardrails → resultado idéntico al de hoy salvo `blocked: False`.
- API: `/v1/agents/{name}/run` devuelve `blocked` y `guardrail`; el `done` del WS también.
- Cada manifiesto de `config/` carga sin warnings de guardrails.

## Fuera de alcance

Clasificadores por LLM o embeddings (categorías, temas permitidos), guardrails sobre
argumentos o resultados de tools, patrones PII por país, y propagación a Cortex/Forge
(su schema y el `GuardrailNode` se ajustan en el release, como siempre, después del core).
