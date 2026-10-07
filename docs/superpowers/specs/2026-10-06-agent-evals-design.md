# Evals de agentes: formato estándar y runner — subproyecto 2c

**Fecha:** 2026-10-06
**Estado:** diseño aprobado en conversación; pendiente de revisión del spec escrito.
**Alcance:** core `astromesh` (`astromesh/evals/` nuevo, entry point `astromesh-eval` en
`pyproject.toml`, `vscode-extension/schemas/eval.schema.json` nuevo, `docs/`)

Primera pieza del resto del subproyecto 2 (contexto y prompts). Las que siguen —optimización
offline con DSPy, compresión con LLMLingua-2, `spec.context` declarativo— necesitan medir si
la calidad se sostiene cuando bajan los tokens. Hoy no hay cómo: el core no tiene evals, y
el único precedente (Nebula, `eval.jsonl` + umbrales en `configs/eval.yaml`) es de
clasificación. Este spec define el formato y un runner que lo ejecuta.

## Decisiones tomadas

1. **Primer uso: el gate del autor.** El core define el formato y un runner que se corre local
   o en CI, y que sale con error si un eval queda bajo su umbral. Nexus y Cortex lo consumen
   después; no es parte de este spec.
2. **Calificación: asserts deterministas más un juez LLM opcional.** El juez sólo se usa en
   los casos que traen `rubric`. Siempre se reportan tokens, caché, costo y latencia, porque
   el objetivo del subproyecto es ver calidad contra ahorro.
3. **Tools con fixtures por caso.** Una tool con fixture no se ejecuta. Una sin fixture corre
   de verdad, salvo `tools_default: block`.
4. **El runner corre in-process.** Arranca su propio `AgentRuntime`. Se descartan dos
   alternativas: ir por la API, que obligaría a aceptar fixtures del llamador (en producción,
   cualquiera podría stubear tools), y un plugin de pytest, que ataría el formato a pytest
   cuando DSPy y Cortex tienen que leerlo sin él.
5. **Sin dependencias nuevas.** `api.main` no importa `astromesh.evals`. `jsonschema` es sólo
   dependencia de desarrollo, así que el cargador valida en Python y no hay assert
   `json_schema`. Si hace falta, se suma con el extra que lo traiga.

## Formato

Un archivo `*.eval.yaml` por eval. Por defecto viven en `<config_dir>/evals/`.

```yaml
apiVersion: astromesh/v1
kind: Eval
metadata:
  name: lucia-basico
spec:
  agent: lucia                  # agente del mismo árbol de config
  judge:                        # opcional; sólo lo usan los casos con `rubric`
    model: {provider: openai_compat, model: kimi-k2, endpoint: "https://api.moonshot.ai/v1", api_key_env: MOONSHOT_API_KEY}
    pass_score: 0.7             # default 0.7
  tools_default: real           # real | block
  thresholds:
    pass_rate: 0.9              # requerido: fracción de casos que pasan
    max_avg_tokens: 6000        # opcional: promedio de tokens_in + tokens_out por caso
  cases:
    - id: stock-simple
      turns:
        - "¿cuánto stock hay de X?"
      context: {prefetch: {stock: 12}}
      tools:
        consultar_stock: {sku: X, stock: 12}
      expect:
        - contains: "12"
        - tool_called: consultar_stock
        - not_contains: "no sé"
      rubric: "Responde con la cantidad y no inventa precios."
  cases_file: lucia.cases.jsonl # opcional, relativo al eval; un caso por línea, misma forma
```

### Reglas

- `spec.agent` y `spec.thresholds.pass_rate` (entre 0 y 1) son requeridos. Tiene que haber
  al menos un caso, sumando `cases` y `cases_file`.
- `judge.model` usa la misma forma que un candidato de `model` en un agente y se construye con
  `build_candidate_provider` (`astromesh/runtime/engine.py`).
- Un caso:
  - `id` es requerido, único dentro del eval, `[a-z0-9_-]{1,64}`;
  - `turns` es requerido: lista de 1 o más strings;
  - `context`, `tools`, `expect` y `rubric` son opcionales;
  - un caso sin `expect` ni `rubric` es un error de carga, porque no puede fallar.
- `context` es el mismo dict que acepta `/v1/agents/{name}/run` y va en todos los turnos.
- `expect` se evalúa sobre la **respuesta del último turno**, salvo `tool_called` y
  `tool_not_called`, que miran **todas** las llamadas del caso.

### Asserts

| Assert | Pasa si |
|---|---|
| `contains: str` | el texto aparece en la respuesta, sin distinguir mayúsculas |
| `not_contains: str` | no aparece, sin distinguir mayúsculas |
| `regex: str` | `re.search` encuentra coincidencia (sensible a mayúsculas; usar `(?i)` si hace falta) |
| `equals: str` | la respuesta, con `.strip()`, es idéntica |
| `tool_called: str` | la tool se llamó al menos una vez en el caso |
| `tool_not_called: str` | no se llamó |

Un assert con una clave desconocida es error de carga.

## Runner

```
astromesh-eval <config_dir> [archivo.eval.yaml ...] [--out reporte.json]
```

Sin archivos, corre todos los `<config_dir>/evals/*.eval.yaml`. Módulo `astromesh/evals/`:

| Archivo | Responsabilidad |
|---|---|
| `formato.py` | Carga y valida un `*.eval.yaml` (más su `cases_file`) a dataclasses |
| `asserts.py` | `chequear(assert, respuesta, tools_llamadas) -> str \| None` (None si pasa, motivo si no) |
| `juez.py` | Arma el prompt del juez, llama al provider y parsea `{"score", "reason"}` |
| `runner.py` | Arranca el runtime, aísla memoria, instala fixtures, corre los casos y arma el reporte |
| `__main__.py` | CLI: argumentos, tabla en consola, `--out`, exit code |

### Arranque

`AgentRuntime(config_dir)` y `bootstrap()`, igual que el lifespan de la API. Si un eval
nombra un agente que no existe, es error de carga.

### Memoria aislada

Antes de correr, cada agente que declara `memory.conversational` pasa a usar un backend
conversacional en memoria (`astromesh/evals/memoria.py`, implementa `ConversationBackend`). Se
asigna en el `MemoryManager` del agente (`_conversation`). Así el eval nunca escribe en Redis
ni en Postgres. Cada caso usa `session_id = eval-<run_id>-<case_id>`, y sus turnos comparten
esa sesión: así se testea la memoria entre turnos.

### Fixtures

El runner envuelve una sola vez el `execute` del `ToolRegistry` de cada agente del árbol.
Envolver todos, y no sólo el del agente evaluado, hace que un sub-agente llamado como tool
también quede stubeado. Las fixtures del caso viajan en un `ContextVar` que el runner fija
antes de cada caso.

- La tool tiene fixture → devuelve una copia profunda. Si el valor no es dict, devuelve
  `{"result": valor}`.
- No hay fixture y `tools_default: block` → `{"error": "tool sin fixture en el eval: <nombre>"}`.
- Si no, ejecuta la tool real.
- Fuera de un caso (`ContextVar` vacío), el wrapper delega sin tocar nada.

El resultado sigue pasando por el recorte de 0.66 (`presentar`), que ocurre después de
`execute`. El gate de confirmación vive en `tool_fn`, antes de `execute`, así que una fixture
no lo saltea: un caso puede testear que el agente pide confirmación, y otro turno puede
responder «SI».

Las tools llamadas se registran por caso con su nombre, desde el mismo wrapper. Eso alimenta
`tool_called` y `tool_not_called` y no depende de la traza.

### Juez

- Prompt fijo con la rúbrica, los turnos del usuario y la respuesta final. Pide sólo JSON
  `{"score": <0..1>, "reason": "<una oración>"}`.
- Pasa si `score >= pass_score`.
- Si el provider falla, la respuesta no es JSON o `score` no es un número entre 0 y 1, el caso
  queda en `error`.
- Un caso con `rubric` en un eval sin `judge` es error de carga.
- Los tokens del juez se reportan aparte (`judge_tokens`) y no entran en los del agente ni en
  `max_avg_tokens`.

### Resultado de un caso

| Estado | Cuándo |
|---|---|
| `pass` | todos los asserts pasan y, si hay rúbrica, el juez aprueba |
| `fail` | algún assert falla o el juez desaprueba; se guardan los motivos |
| `error` | la corrida del agente levanta o el juez no da un veredicto válido |

`error` cuenta como no aprobado en `pass_rate`. Un caso que levanta no corta el eval.

Por caso se guardan: `id`, `status`, `motivos` (lista), `judge` (`score`, `reason`) si hubo,
`tokens_in`, `tokens_out`, `cached_tokens`, `cost`, `latency_ms`, `judge_tokens`,
`tools_llamadas`, `answer`. Los tokens y el costo salen de `usage_from_trace`
(`astromesh/api/usage.py`) sobre la traza de cada turno, sumados.

### Reporte y salida

- Consola: una tabla por eval (caso, estado, tokens, costo, latencia) y una línea de agregado:
  `pass_rate`, tokens promedio, costo total y si cumple los umbrales.
- `--out`: JSON con `{"run_id", "evals": [{"name", "agent", "passed", "pass_rate",
  "avg_tokens", "total_cost", "cases": [...]}]}`.
- Exit code: `0` si todos los evals cumplen sus umbrales, `1` si alguno no, `2` por error de
  carga (YAML inválido, agente inexistente, rúbrica sin juez). Con error de carga no se corre
  ningún caso.

## Schema

`vscode-extension/schemas/eval.schema.json`, con `additionalProperties: false` como el de
agentes, cubriendo `apiVersion`, `kind: Eval`, `metadata.name` y `spec`. Es para el editor:
el runtime no depende de `jsonschema`, así que `formato.py` valida todas las reglas en Python.
Un test valida los evals de ejemplo contra el schema y prueba que el schema y el cargador
rechazan las mismas formas inválidas.

## Fuera de alcance

- Concurrencia, repeticiones por caso y comparar dos manifiestos (A/B). Los suma DSPy cuando
  los necesite.
- Comando en `astromeshctl` y soporte en Nexus o Cortex.
- Métricas de RAG (recall, faithfulness).

## Docs

Página nueva `docs-site/src/content/docs/advanced/evals.md` con el formato, los asserts, las
fixtures y el uso en CI. También va la sección correspondiente en `docs/CONFIGURATION_GUIDE.md`.
Se publica cuando el feature salga en un release, no antes.

## Tests

1. **Carga:**
   - un eval válido, con `cases_file` incluido, carga;
   - cada una de estas da error de carga: `id` duplicado, assert desconocido, `rubric` sin
     `judge`, caso sin `expect` ni `rubric`, agente inexistente, `pass_rate` fuera de 0..1.
2. **Asserts:** cada uno pasa y falla, incluido `contains` sin distinguir mayúsculas.
3. **Fixtures:**
   - una tool con fixture no ejecuta su handler y el modelo recibe el valor;
   - un valor no dict llega envuelto en `{"result": ...}`;
   - con `tools_default: block`, una tool sin fixture devuelve el error y no ejecuta;
   - fuera de un caso, el wrapper ejecuta la tool real.
4. **Memoria:**
   - dos turnos del mismo caso comparten historial;
   - dos casos no se ven entre sí;
   - después de preparar el runtime, el backend conversacional de cada agente con memoria es
     el de memoria del eval, y los turnos quedan ahí (el backend Redis se construye al
     arrancar, porque es lazy, pero nunca recibe una escritura).
5. **Juez:**
   - un score sobre el umbral aprueba y uno bajo desaprueba;
   - una respuesta que no es JSON deja el caso en `error`;
   - los tokens del juez no se suman a los del agente.
6. **Runner:**
   - un caso que levanta queda en `error` y el siguiente corre;
   - `pass_rate` y `max_avg_tokens` deciden el exit code;
   - un error de carga sale con 2 sin correr casos.
7. **Reporte:** `--out` escribe el JSON con la forma documentada.
8. **Schema:** el eval de ejemplo valida contra `eval.schema.json`, y las formas inválidas de (1) que son de forma (assert desconocido, `pass_rate` fuera de rango) también las rechaza el schema.

Todos los tests usan providers falsos (`model_fn` stub, como en `tests/test_engine*`), así que
no hacen llamadas de red.
