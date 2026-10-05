# Contexto conversacional con presupuesto real — subproyecto 1 de 2

**Fecha:** 2026-10-05
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Alcance:** core `astromesh` (`astromesh/core/memory.py`, `astromesh/core/tokens.py` nuevo,
`astromesh/runtime/engine.py`, `astromesh/memory/strategies/`, `vscode-extension/schemas/agent.schema.json`)

Este es el primero de dos subproyectos sobre optimización de contexto y de prompts. El
segundo (estandarizar `spec.context`, compresión, caché explícito, optimización offline de
prompts) tiene su propio spec y arranca cuando éste esté en `develop`. Ver «Fuera de alcance».

## Problema

`spec.memory.conversational` promete estrategias (`sliding_window`, `summary`,
`token_budget`) que hoy no funcionan:

1. **`token_count` nunca se carga.** `engine.py` persiste los turnos sin él, así que vale 0.
   `token_budget` mete el historial completo (cada turno «cuesta» 0) y `sliding_window` no
   descuenta nada del presupuesto.
2. **`summary` no resume.** `MemoryManager` acepta `summarize_fn`, pero nadie se la pasa, así
   que `get_summary` devuelve siempre `None`.
3. **El presupuesto está fijo.** `build_context(..., max_tokens=4096)` no conoce la ventana
   del modelo ni descuenta el system prompt, las tools o la respuesta.
4. **El historial no llega al modelo como mensajes.** `ReActPattern` y `GlyphPattern` leen
   `context["_history_messages"]`, pero nadie carga esa clave (lo reconoce
   `tests/test_glyph_engine.py:190`). Un agente sólo «recuerda» si su template mete
   `{% for t in memory.conversation %}` dentro del system prompt, como hacen los manifiestos
   de OFFICIUM/Clarus.
5. **Por (4), el caché de prompts no funciona en conversaciones largas.** Esos templates
   cambian el system prompt en cada turno, así que el prefijo nunca es estable.
6. **Código muerto.** `astromesh/memory/strategies/{sliding_window,summary,token_budget}.py`
   no los usa nadie. `MemoryManager.build_context` tiene su propia copia en línea.

## Decisiones tomadas

1. **El historial viaja como mensajes y el template queda como camino legado.** El runtime
   carga `_history_messages`. Si el system prompt usa `memory.conversation`, se respeta ese
   camino y no se duplica el historial (ver «Entrega»).
2. **El presupuesto se deriva de la ventana del modelo.** El orden de resolución está en
   «Ventana».
3. **El conteo de tokens es propio y no suma dependencias al core.** `api.main` tiene que
   seguir importando sin extras, porque si no la imagen de astromesh-os no bootea.
4. **El resumen lo hace un rol del agente.** Se usa `model.roles.summarizer` si existe y
   `default` si no. No se adopta una librería de memoria externa (mem0, Zep, Letta), porque
   cualquiera de ellas sería una segunda arquitectura de memoria superpuesta a la nuestra.

## Diseño

### Ventana

Se resuelve **una vez, al cargar el agente**, para cada candidato del rol `default`. Gana el
primero de estos que dé un valor:

1. `context_window` declarado en el candidato (campo nuevo, entero opcional).
2. `parameters.num_ctx` si `provider: ollama`.
3. `litellm.get_model_info(model)["max_input_tokens"]` si el extra `litellm` está instalado.
   Cualquier excepción se trata como «no dio valor».
4. Si ninguno da valor, la ventana es **desconocida**: el historial NO se recorta por
   presupuesto (sólo por `max_turns`, como antes del fix) y el agente emite un warning al
   cargar (si declara `memory.conversational`) pidiendo declarar `context_window`. Se aparta
   del default de 32k original para no recortar en silencio a modelos que litellm no conoce
   (p. ej. `kimi-*` vía `openai_compat`).

La ventana efectiva del agente es la **mínima** entre los candidatos de `default`, para que un
fallback más chico no desborde. Se guardan el valor y la fuente del candidato que la fijó.

### Conteo — `astromesh/core/tokens.py`

```python
def estimate_tokens(text: str, model: str | None = None) -> int
```

- Con litellm instalado y `model` dado, usa `litellm.token_counter`. Cualquier excepción cae
  al paso siguiente, con un log en debug.
- Si no, devuelve `ceil(len(text) / 4)`.

Al persistir, los dos turnos usan `estimate_tokens(contenido)`. **No se usa `output_tokens`
del proveedor:** en ReAct se acumula entre iteraciones (incluye las vueltas de tools) y en
los modelos de razonamiento incluye el razonamiento, que no se reenvía. Lo que ocupa el
contexto en el turno siguiente es el texto de la respuesta.

Al leer, un turno con `token_count == 0` (filas viejas) se estima en el momento. No hay
migración de datos.

### Presupuesto y selección — dentro de `Agent.run`, reemplaza `max_tokens=4096`

1. Se calculan semántica, episódica y RAG igual que hoy.
2. **Base.** Se renderiza el system prompt con `memory.conversation = []` y se le suman
   `estimate_tokens(system)`, `estimate_tokens(json.dumps(tool_schemas))` y el `max_tokens`
   de respuesta del candidato primario (shorthand o `parameters`; 1024 si no está declarado).
3. **Presupuesto del historial:** `max(0, int(ventana * 0.9) - base)`.
4. **Selección:**
   - `sliding_window`: los últimos `max_turns` y después el recorte por presupuesto.
   - `token_budget`: sólo el recorte por presupuesto.
   - `summary`: el recorte por presupuesto. Si hay un resumen guardado (sólo existe cuando
     el historial ya superó `max_turns`, así que siempre cubre turnos que quedaron afuera),
     entra como primer mensaje (`role: user`, prefijo
     `[Resumen de la conversación anterior]`), y sus tokens se descuentan antes de elegir
     los turnos.
   - El recorte usa `TokenBudgetStrategy` (ruta Rust incluida), que pasa a ser el único
     implementador. Su fallback por palabras se reemplaza por `estimate_tokens`.

### Entrega

- **El system prompt contiene el texto `memory.conversation`** (chequeo de substring sobre el
  template sin renderizar): se vuelve a renderizar con los turnos seleccionados y **no** se
  cargan mensajes. Se emite un warning una vez por agente: *historial en el system prompt:
  rompe el caché de prompts; migrá a mensajes*.
- **En cualquier otro caso:** los turnos seleccionados se convierten a
  `{"role", "content"}` y van a `context["_history_messages"]`. `memory.conversation` sigue
  disponible en Jinja, igual que hoy.

### Resumen

- Se cablea `summarize_fn` en `MemoryManager`: una llamada al router del rol `summarizer`, o
  `default` si no existe, con un prompt fijo de resumen sobre los turnos viejos.
- Se dispara donde ya está (`persist_turn`, cuando el historial supera `max_turns`) y **sólo
  si `strategy: summary`**.
- Si falla, se registra un warning y se mantiene el resumen anterior. La respuesta ya se
  entregó.

### Código muerto

Se borran `astromesh/memory/strategies/sliding_window.py` y `summary.py`, junto con sus tests
si los hay. `token_budget.py` se mantiene y pasa a usarse.

## Errores

Ningún paso de contexto hace fallar una corrida, con el mismo criterio que
`agent_rag.build_context`.

| Situación | Comportamiento |
|---|---|
| La base supera la ventana | Presupuesto 0, historial vacío, warning con las cifras; la corrida sigue y el proveedor decide |
| Falla el resumen | Warning; queda el resumen anterior |
| Falla `token_counter` / `get_model_info` | Se pasa a la siguiente fuente sin avisar (debug log) |

## Compatibilidad

- **Schema:** `context_window` (integer, minimum 1) en `$defs/modelConfig` de
  `vscode-extension/schemas/agent.schema.json`. Sin esto, el manifiesto se rechaza, porque
  `additionalProperties: false`.
- **OFFICIUM/Clarus:** siguen andando por el camino legado, ahora con presupuesto real y con
  el warning de migración.
- **Cambio de comportamiento:** los agentes con `memory.conversational` cuyo template no usa
  `memory.conversation` **empiezan a recibir el historial**. Va en el CHANGELOG bajo `Fixed`,
  dicho explícitamente.
- **Seguimiento (fuera de este spec):** el schema de Cortex se mantiene a mano y hay que
  sumarle `context_window`.

## Observabilidad

Atributos en un span nuevo, `context_fit`, hijo de `prompt_render`. No van en `memory_build`
porque el recorte ocurre después de medir el system prompt:

`context.window`, `context.window_source`, `context.base_tokens`, `history.budget`,
`history.turns_kept`, `history.turns_dropped`, `history.tokens`, `history.delivery`
(`messages` | `template`), `history.summary_used`.

## Tests

Cada uno falla contra el `develop` actual:

1. Los dos turnos persistidos (usuario y asistente) tienen `token_count > 0`.
2. `token_budget` con un historial que no entra en el presupuesto recorta.
3. Un agente con `memory.conversational` y sin `memory.conversation` en el template recibe los
   turnos previos en los `messages` del segundo `model_fn`.
4. Un agente con `memory.conversation` en el template no recibe mensajes de historial y emite
   el warning.
5. `strategy: summary` llama al rol `summarizer`, y el resumen es el primer mensaje cuando
   hay turnos recortados.
6. Resolución de la ventana: YAML > `num_ctx` > litellm > desconocida (sin recorte por
   presupuesto), y el mínimo entre candidatos.
7. Si la base supera la ventana, no hay excepción y el historial queda vacío.
8. El system prompt enviado es idéntico entre el turno 1 y el turno 2 de un agente que recibe
   el historial por mensajes (prefijo estable para el caché).

## Fuera de alcance (subproyecto 2)

- `spec.context` declarativo y estándar en el YAML.
- Presupuesto y deduplicación para RAG, semántica y episódica.
- Compresión con LLMLingua-2, como extra opcional `compression`.
- Marcadores `cache_control` y orden canónico del prompt para el caché.
- Optimización offline de prompts (DSPy GEPA/MIPROv2) fuera del runtime, con un formato de
  eval estándar.
