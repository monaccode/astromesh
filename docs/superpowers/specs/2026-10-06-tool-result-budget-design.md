# Tope por observación de tool — subproyecto 2b

**Fecha:** 2026-10-06
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Alcance:** core `astromesh` — `astromesh/orchestration/observaciones.py` (nuevo),
`astromesh/orchestration/patterns.py` (`ciclo_de_tools`, `AgentStep`, patrones que lo llaman),
`astromesh/orchestration/supervisor.py`, `astromesh/runtime/engine.py`,
`vscode-extension/schemas/agent.schema.json`.

Sigue a los subproyectos 1 (`2026-10-05-context-budget-fix-design.md`) y 2a
(`2026-10-05-prompt-cache-prefix-design.md`). Reemplaza el «presupuesto para RAG» que estaba
planeado como 2b: medido contra producción, el RAG del core (`spec.knowledge`) casi no se usa y la
memoria semántica/episódica no está cableada; lo que de verdad pesa son los **resultados de tools**.

## Problema

`ciclo_de_tools` (`patterns.py`, compartido desde astromesh 0.65.0 por ReAct, plan_and_execute,
pipeline, fan_out y supervisor) mete cada resultado de tool en `messages` así:

```python
messages.append({"role": "tool", "content": str(observation), "tool_call_id": tc["id"]})
```

1. **Sin tope.** Un listado de PRAXIS, una búsqueda en documentos o la respuesta de un sub-agente
   entran enteros. Un resultado patológico (decenas de miles de caracteres) se paga entero y ocupa
   ventana.
2. **`str()` de un dict/lista es el repr de Python** (`{'a': True, 'b': None}`), no JSON.

Lo que NO es el problema: dentro de una corrida los mensajes sólo se agregan al final, así que en
las vueltas siguientes las observaciones anteriores las sirve el caché de prefijo (precio de caché);
y entre turnos no se acumulan (al historial sólo se persisten la query y la respuesta). El costo real
de una observación gigante es **la primera vez y la ventana**.

## Decisiones tomadas

1. **Tope en el momento en que la observación entra**, en `ciclo_de_tools`. No se reescriben
   observaciones anteriores (rompería el prefijo cacheado) ni se resumen con un modelo.
2. **Recorte que respeta la estructura**: listas pierden elementos del final con un aviso; un dict
   recorta su lista más grande; el texto pierde la cola con un marcador. Nunca JSON inválido.
3. **Serialización canónica JSON** en lugar del repr de Python.
4. **Glyph no se toca**: sus programas reciben los resultados como datos y recortarlos cambiaría lo
   que calculan. El tope vive donde el resultado se vuelve mensaje para el modelo, no en `tool_fn`.
5. **Presupuesto configurable**: por tool, por agente, y un default del runtime de **8000 tokens**
   (generoso a propósito: cortar lo patológico, no lo normal).

## Diseño

### 1. `astromesh/orchestration/observaciones.py`

```python
DEFAULT_MAX_TOOL_RESULT_TOKENS = 8000

def presentar(observacion, max_tokens: int) -> tuple[str, dict]:
    """El texto que ve el modelo y los datos del recorte para la traza."""
```

El dict de retorno: `{"tokens": int, "truncated": bool, "omitted": int}` — `tokens` es el tamaño
estimado del resultado ORIGINAL serializado (`estimate_tokens`), `omitted` la cantidad de elementos
de lista omitidos (0 si no aplica).

Algoritmo:

1. Serializar: `str` → tal cual; cualquier otro → `json.dumps(obs, ensure_ascii=False,
   separators=(",", ":"), default=str)`.
2. Si `estimate_tokens(texto) <= max_tokens` → devolverlo tal cual (`truncated: False`).
3. Si no:
   - **lista** → conservar el prefijo más largo de elementos tal que la lista recortada más el
     elemento aviso `{"_omitidos": N, "_nota": "resultado recortado: hay N elementos más; pedí un
     filtro más específico"}` entre en el presupuesto;
   - **dict** cuyo valor más grande (en tokens serializados) es una lista → recortar esa lista del
     mismo modo, con el aviso como último elemento, dejando el resto del dict intacto;
   - si tras eso sigue sin entrar, o es texto, o es otro tipo → recorte de texto sobre la cadena
     serializada: conservar la cabeza y agregar `\n[resultado recortado: X de Y tokens]`.
4. El recorte por estructura siempre produce JSON válido (se re-serializa el objeto recortado).

**Nunca lanza:** cualquier excepción interna cae a `str(observacion)` con recorte de texto y un log
en debug.

### 2. `ciclo_de_tools`

- Nuevo parámetro opcional `presupuesto: dict | None = None` con la forma
  `{"default": int, "por_tool": {nombre: int}}` (sin él → `DEFAULT_MAX_TOOL_RESULT_TOKENS`).
- Para cada tool call: `texto, recorte = presentar(observation, max_tokens_de(tc["name"]))`; el
  mensaje `tool` lleva `texto`; el `AgentStep` guarda `observation=texto` y un campo nuevo
  `recorte: dict | None` (sólo si `truncated`).
- La observación por tool no permitida (`permitidas`) pasa igual por `presentar` (es un string corto).
- Todos los patrones que llaman a `ciclo_de_tools` (ReAct, plan_and_execute, pipeline, fan_out,
  supervisor) le pasan `presupuesto=context.get("_presupuesto_tools")` (con el guard
  `isinstance(context, dict)` que ya usan). Swarm tiene su propio loop: fuera de alcance (anotado).

### 3. Engine

- Al cargar el agente se arma el mapa: `default` = `orchestration.max_tool_result_tokens` si es un
  entero > 0, si no `DEFAULT_MAX_TOOL_RESULT_TOKENS`; `por_tool[nombre_registrado]` =
  `tools[].max_result_tokens` si es un entero > 0. Valores inválidos (0, negativos, no enteros) → se
  ignoran con un warning al cargar que nombra agente, tool y valor.
- En `Agent.run`: `memory_context["_presupuesto_tools"] = <mapa>` (mismo canal que
  `_turn_context`; se escribe después de todos los renders, ningún template lo ve).
- `_CLAVES_POR_TIPO`: `max_result_tokens` permitida en **todos** los tipos de tool (no dispara el
  aviso de clave ignorada). El nombre registrado de la tool (p. ej. `<slug>_<acción>` en
  integraciones) es la clave de `por_tool`; para tipos que registran varias tools desde una
  definición (integration, api, mcp) el valor aplica a todas las que esa definición registra.
- Traza: el span `tool.call` suma `tool.result_tokens` (tamaño estimado del resultado crudo). Al
  volcar los `steps` a la traza (`step_data`), un step con `recorte` suma `truncated: true` y
  `omitted: N`.

### 4. Schema

`vscode-extension/schemas/agent.schema.json`: `max_result_tokens` (integer, minimum 1) en cada tipo
de tool que el schema define, y `max_tool_result_tokens` (integer, minimum 1) en
`orchestration`.

## Compatibilidad

- **repr → JSON**: el modelo ve JSON en lugar del repr de Python para resultados dict/list. Cambio de
  comportamiento visible, va en el CHANGELOG; los tests que fijaban el repr se actualizan.
- Manifiestos actuales: sin cambios necesarios (rige el default de 8000).
- **Fuera del core (seguimiento):** el schema de Cortex (mantenido a mano) y la copia vendorizada en
  `clarus-limen/apps/agents-clarus/.../astromesh_contract/agent.schema.json` tienen
  `additionalProperties: false`: no aceptarán las claves nuevas hasta su paridad. El pool de Nexus
  sube a la versión que lo libere.

## Errores

| Situación | Comportamiento |
|---|---|
| Fallo interno al serializar/recortar | `str(observacion)` con recorte de texto; log debug; la corrida sigue |
| Presupuesto inválido en el YAML | Warning al cargar; se usa el default |
| Resultado no serializable a JSON | `default=str` |

## Tests

1. `presentar`: string que entra; string que no entra (marcador con X de Y); lista que entra; lista
   que no entra (prefijo + `_omitidos`, `json.loads` válido, `omitted` correcto); dict con lista
   grande (recorta esa lista, resto intacto); dict sin listas que no entra (recorte de texto);
   objeto no serializable (`default=str`); `tokens` = tamaño original.
2. `ciclo_de_tools` usa `por_tool` cuando existe y el `default` si no; sin `presupuesto` usa
   `DEFAULT_MAX_TOOL_RESULT_TOKENS`; el `AgentStep` trae `recorte` sólo cuando hubo recorte.
3. Un resultado dict llega al modelo como JSON (no repr).
4. Glyph: un programa que cuenta los elementos de una lista grande devuelve el número real (sin
   recorte).
5. Engine de punta a punta: `tools[].max_result_tokens` y `orchestration.max_tool_result_tokens`
   llegan al mensaje `tool`; valor inválido → warning y default; las claves no disparan el aviso de
   clave ignorada en ningún tipo de tool.
6. Traza: `tool.call` con `tool.result_tokens`; el step recortado con `truncated`/`omitted`.
7. Los patrones plan_and_execute, pipeline, fan_out y supervisor pasan el presupuesto (un test por
   patrón con un resultado grande).

## Release y docs

- Core **0.66.0** (0.65.0 ya liberada por otra sesión).
- Docs (después de implementar): `configuration/agent-yaml.md` (las dos claves), una línea en
  `advanced/prompt-caching.md` y `advanced/observability.md` (atributos nuevos).

## Fuera de alcance

- Envejecer/resumir observaciones anteriores dentro de la corrida (rompe el caché).
- Resumir resultados con un modelo.
- Swarm (loop propio).
- Presupuesto y deduplicación de RAG, memoria semántica y episódica (sin uso en producción hoy).
