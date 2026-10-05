# Prefijo estable para el caché de prompts: `prompts.context` — subproyecto 2a

**Fecha:** 2026-10-05
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Alcance:** core `astromesh` (`astromesh/runtime/engine.py`, `astromesh/orchestration/patterns.py`,
`astromesh/orchestration/glyph_pattern.py`, `vscode-extension/schemas/agent.schema.json`,
`docs/CONFIGURATION_GUIDE.md`)

Sigue a `2026-10-05-context-budget-fix-design.md` (subproyecto 1, ya en `develop`), que dejó
el historial viajando como mensajes y el system prompt estable entre turnos **siempre que el
template no meta nada que cambie por query**. Este spec resuelve ese "siempre que".

## Problema

Casi toda la flota corre Kimi vía `openai_compat` (Moonshot). Ese caché es **automático por
prefijo**: el proveedor sirve desde caché los tokens iniciales que coinciden con una llamada
anterior (medido el 2026-09-04: bloques de 4096, hasta 86-88% del prompt con prefijo estable).
No hay que marcar nada; hay que no romper el prefijo.

Hoy el prefijo se rompe en cada query para todo agente con RAG o `prefetch`:

1. `knowledge` (RAG) y `prefetch` **sólo** llegan al modelo si el template de `prompts.system`
   los referencia. No hay otro lugar donde ponerlos.
2. Entonces el system prompt —el primer mensaje— cambia con cada query, y desde ahí no se
   cachea nada: ni el resto del system, ni las tools, ni el historial.

`cache_control` explícito (Anthropic vía litellm) queda **fuera** de este spec: hoy no hay
agentes Claude en producción.

## Decisiones tomadas

1. **Un template nuevo, opcional: `prompts.context`.** `prompts.system` queda para lo
   estable; `prompts.context` para lo que cambia por turno. Lo decide el autor; el runtime no
   reubica variables por su cuenta (descartado: duplicaría contenido en manifiestos que ya
   referencian `knowledge` y quitaría control del formato).
2. **El contexto va al final, pegado al mensaje del usuario actual.** Orden resultante:
   system → tools → historial → [gramática glyph] → **contexto + query**. Todo lo anterior al
   último mensaje es prefijo estable.
3. **Lo persistido no cambia:** el turno de usuario se guarda con la query original, sin el
   bloque de contexto, así el RAG no se acumula en la memoria.
4. **Patrones sin soporte no pierden contenido:** el contexto se agrega al final del system
   (comportamiento equivalente al actual, sin ganancia de caché) y se avisa al cargar.

## Diseño

### Manifiesto

```yaml
prompts:
  system: |
    Sos Lucía, analista comercial...
  context: |
    {% if knowledge %}DOCUMENTOS RELEVANTES:
    {{ knowledge }}{% endif %}
    {% if prefetch.stock %}STOCK ACTUAL: {{ prefetch.stock }}{% endif %}
```

Schema: `prompts.context` (string) en `vscode-extension/schemas/agent.schema.json`
(`properties.spec.properties.prompts`, que tiene `additionalProperties: false`).

### Render — `Agent.run`

- `prompts.context` se renderiza con **las mismas variables** que el system (`knowledge`,
  `prefetch`, `memory`, el `context` del llamador) y el mismo `PromptEngine` sandbox. No lleva
  el bloque de `output_schema` (eso es del system).
- Se hace en el bloque `prompt_render`, después del render base del system y **antes** de
  calcular el presupuesto del historial: los tokens del contexto (`estimate_tokens`) se suman
  a `base_tokens`, porque ocupan ventana.
- Resultado vacío tras `.strip()` → no hay contexto.
- Entrega según el patrón (lista única en el engine, `_PATTERNS_WITH_TURN_CONTEXT =
  {"react", "glyph"}`):
  - patrón en la lista → `memory_context["_turn_context"] = texto` (mismo canal que
    `_history_messages`; el patrón lo recibe dentro de su `context`);
  - otro patrón → `rendered_prompt += "\n\n" + texto` (al final del system).

### Helper — `astromesh/orchestration/patterns.py`

```python
def with_turn_context(query, turn_context):
    """La query del usuario con el contexto del turno adelante, o intacta si no hay."""
```

- sin contexto (None / vacío) → `query` sin tocar;
- `query` string → `f"{turn_context}\n\n{query}"`;
- `query` lista (multimodal) → `[{"type": "text", "text": turn_context}, *query]`.

### Patrones

- **ReAct:** `messages = [*history, {"role": "user", "content": with_turn_context(query, ctx)}]`
  con `ctx = context.get("_turn_context")`.
- **Glyph:** el mensaje de la query (después del bloque de gramática, que queda igual) y el
  mensaje de la query en la llamada de narración usan `with_turn_context(query, ctx)`. `env`
  del programa no cambia: `env["query"]` sigue siendo la query original.

### Warnings al cargar (`_build_agent`)

- `prompts.system` referencia variables que cambian por query → warning sugiriendo moverlas a
  `prompts.context`. Detección con una regex al estilo de `_history_in_template`:
  `\b(knowledge|prefetch)\b|memory\.(semantic|episodic)\b` (no matchea `knowledge_base_id`
  ni `memory.conversation_summary`).
- `prompts.context` declarado y patrón fuera de `_PATTERNS_WITH_TURN_CONTEXT` → warning: el
  contexto va al system y no hay ganancia de caché.

## Errores

| Situación | Comportamiento |
|---|---|
| Acceso bloqueado (SSTI) en `prompts.context` | La corrida falla, igual que en `prompts.system` (decisión de seguridad del `PromptEngine`) |
| Variable indefinida | Renderiza vacío, como siempre |
| Contexto vacío tras render | No se agrega nada; la query viaja intacta |
| `input_tokens` 0 al calcular `cache.hit_ratio` | Ratio 0 |

## Observabilidad

- Span `llm.complete`: `cache.hit_ratio = round(cached_tokens / input_tokens, 3)` (0 si
  `input_tokens` es 0).
- Span `context_fit`: `turn_context.tokens` (0 si no hay) y `turn_context.delivery`
  (`message` | `system` | `none`).

## Compatibilidad

- Manifiestos sin `prompts.context`: sin cambios de comportamiento.
- System prompts que ya usan `knowledge`/`prefetch`: siguen igual, con el warning.
- OFFICIUM/Clarus: `prompts.context` funciona, pero el prefijo sigue roto mientras el system
  traiga `memory.conversation` (camino legado del subproyecto 1).

## Seguimiento fuera del core (no se implementa acá)

1. **Generador de Cortex/Nexus (OFFICIUM/Clarus):** sacar `{% for t in memory.conversation %}`
   del system y mover "LOS DOCUMENTOS" a `prompts.context`. Es la mayor ganancia de caché para
   la flota actual.
2. **Schema de Cortex (mantenido a mano):** sumar `prompts.context` y `context_window`
   (pendiente también del subproyecto 1).

## Tests

1. `with_turn_context`: query string, query multimodal, contexto vacío/None.
2. ReAct: el último mensaje es contexto + query; el system enviado es idéntico entre dos
   corridas con `knowledge` distinto.
3. Glyph: la query y la narración llevan el contexto; el bloque de gramática queda antes y sin
   tocar; `env["query"]` es la query original.
4. El turno de usuario persistido es la query original, sin el contexto.
5. Los tokens del contexto entran en la base del presupuesto: con ventana chica, un contexto
   grande deja menos historial.
6. Un patrón sin soporte (`plan_execute`) recibe el contexto al final del system, con warning
   al cargar.
7. Warning de variables por query en el system: sale para `knowledge`, `prefetch`,
   `memory.semantic`; no sale para `knowledge_base_id` ni `memory.conversation_summary`.
8. `cache.hit_ratio` en el span, incluido `input_tokens = 0`.
9. SSTI en `prompts.context` hace fallar la corrida.

## Docs

`docs/CONFIGURATION_GUIDE.md`: `prompts.context` con el ejemplo de RAG y el orden del prompt
para el caché.

## Fuera de alcance

- `cache_control` explícito (Anthropic/Bedrock/Vertex vía litellm).
- Presupuesto y deduplicación de RAG, semántica y episódica; compresión (LLMLingua-2).
- Optimización offline de prompts (DSPy).
- `spec.context` declarativo.
