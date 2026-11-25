# Code Mode en el ecosistema Astromesh — Diseño

**Fecha:** 2026-11-25 · **Estado:** aprobado (Juan Carlos, 2026-11-25): enfoque A, nivel 2 del eval como compuerta dura, fase 2 fuera de este plan.

## 1. Intención

Estar preparados para **Code Mode**: la forma de usar tools en la que el modelo, en vez de hacer una tool
call por turno, escribe un programa corto contra una API tipada y ese programa corre en un sandbox. Lo
publicamos como componente Astromesh, la librería **`astromesh-codemode`**, que cualquier framework puede
usar y que el core de Astromesh usa **de forma opcional**, como hicimos con OKF, RAG, Context y A2A.

**Por qué ahora:** Cloudflare, Anthropic, OpenCode, Goose, smolagents y Pydantic AI convergieron en esta
arquitectura durante 2026. MCP no desaparece (sigue poniendo conexión, autorización y documentación); lo
que cambia es cómo se le presentan las tools al modelo. Queremos tenerlo antes de que un cliente lo pida.

**Éxito:**
- En ≤5 líneas, un agente de LangChain/LangGraph, PydanticAI, OpenAI Agents SDK, Google ADK, CrewAI,
  LlamaIndex, smolagents o Microsoft Agent Framework envuelve servidores MCP o funciones Python en Code
  Mode y recibe dos tools: `search` y `run`.
- Un servidor MCP de la librería (`astromesh-codemode mcp …`) se pone delante de otros servidores MCP y
  los expone en Code Mode a Claude, Cursor o cualquier cliente MCP, sin escribir código.
- **Un eval publicado dice dónde gana y dónde pierde** frente a tool calling directo, por tamaño de
  catálogo y de datos intermedios. Nada de "ahorra X%" sin esa tabla.
- El sandbox detiene el 100% de las trampas del eval de seguridad con la configuración por defecto.
- En Astromesh, `type: codemode` agrupa tools del agente detrás de `search`/`run`, sin cambiar el patrón
  de orquestación y sin saltarse permisos, compuertas de confirmación, rate limits ni traces.

**Anti-objetivos (un fracaso aunque funcione):**
- Prometer ahorro que no medimos. Glyph ya nos enseñó que "el modelo escribe un programa" puede costar
  entre +164% y +2839% más que ReAct.
- Que el código del modelo pueda tocar algo del host que no le pasamos explícitamente.
- Que Code Mode sirva para saltarse una compuerta de confirmación (`confirm`), los `permissions` o el
  `origen` de un turno.
- Un fallback silencioso: si el sandbox no está, el agente no carga; no se degrada a tool calling sin avisar.
- Reemplazar MCP o Glyph. Glyph sigue siendo la opción para programas fijos (costo cero por corrida).

**Fuera de alcance de la v0.1:** TypeScript/JavaScript como lenguaje del programa, sandbox en contenedor o
remoto, búsqueda semántica con embeddings, tools que escriben (ver 3.4), estado persistente entre `run`s,
streaming del resultado.

## 2. Contexto (medido)

- **Code Mode hoy.** Cloudflare (sep-2025; feb-2026 un servidor MCP para sus +2.500 endpoints en ~1.000
  tokens con dos tools, `search` y `execute`, sobre V8 isolates). Anthropic, "code execution with MCP"
  (descubrimiento progresivo, tools como archivos). OpenCode 2.0 lo usa por defecto. smolagents
  `CodeAgent`. Pydantic AI tiene Code Mode sobre Monty. Alternativa sin ejecutar código: descubrimiento
  dinámico de tools (Speakeasy reporta hasta 160× menos tokens).
- **Dónde dice ganar:** catálogos grandes (los schemas no entran todos al contexto) y datos intermedios
  grandes (no pasan por el modelo: el programa los filtra y devuelve sólo el resultado).
- **Glyph (nuestro):** lenguaje propio; el modelo escribe el programa. Medido contra tres modelos con
  catálogos chicos: más caro que ReAct cuando el modelo lo escribe en cada corrida; −100% con
  `spec.program` fijo. La gramática explicada en el prompt fue parte del costo. Code Mode usa Python, que
  el modelo ya conoce, y apunta a catálogos grandes: no es el escenario que medimos, por eso el eval.
- **Sandbox:** `pydantic-monty` 1.7.0 (MIT, Python ≥3.11): intérprete de un subconjunto de Python escrito
  en Rust, en proceso, sin contenedor. Parsea, chequea tipos contra stubs, compila y ejecuta; cada vez que
  el código llama a una función externa vuelve a Python. El código sólo puede tocar las funciones que le
  pasamos: no hay `import os`, archivos ni red.
- **Core hoy:** tipos de tool `builtin`, `agent`, `client`, `integration`, `api`, `mcp`, `a2a`
  (`engine.py` ~1220–1320). `mcp` registra cada tool del servidor como tool interna con nombre
  `servidor_tool`; las que escriben pasan por `handler_de_propuesta` (compuerta). `a2a` entra por extra
  opcional (`astromesh[a2a]`, `astromesh/integrations/a2a.py`) y sin el extra el agente queda en draft
  con el motivo. Hay budget de resultado de tools (core 0.66+), permisos por fnmatch (0.71+) y `origen`.
- **Librerías hermanas** (`astromesh-a2a`, `-context`, `-rag`, `-okf`): repo propio, Apache-2.0, deps
  mínimas, un extra por framework, servidor MCP, README + README.es, `docs/`, `examples/`, `assets/`, CI y
  PyPI con trusted publishing, un eval en CI.

## 3. La librería `astromesh-codemode`

### 3.1 Enfoque

**Un envoltorio de tools** (enfoque A). Se le da un grupo de tools y devuelve **dos** tools para el modelo:

- `search(query: str, limit: int = 8) -> str` — firmas Python tipadas (stubs) y una línea de descripción
  de las tools que coinciden. El modelo pide sólo lo que necesita: el catálogo entero nunca entra al
  contexto.
- `run(code: str) -> str` — ejecuta el programa en Monty. Cada tool del grupo es una función async
  disponible en el programa; llamarla ejecuta la tool real. Al modelo vuelve sólo lo que el programa
  devuelve (y lo que imprime), con tope de tamaño.

Descartados: un patrón de orquestación (`pattern: codemode`, casi Glyph de nuevo y todo-o-nada por
agente) y extender Glyph (DSL que ningún modelo conoce ni ningún framework adoptaría).

### 3.2 Módulos

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `catalog` | Normaliza fuentes de tools a `ToolSpec` (nombre, descripción, JSON Schema de entrada y salida si hay). Genera stubs Python (`async def nombre(arg: tipo, …) -> tipo`) y el índice de búsqueda (léxico, BM25 sobre nombre + descripción + nombres de parámetros). | — |
| `sources` | Fuentes: funciones Python (sync/async con type hints), servidores MCP (stdio / streamable HTTP), y `ToolSpec` + handler crudo (lo que usa el core). | `mcp` (extra) |
| `sandbox` | Corre el programa en Monty con los stubs: límites de tiempo, memoria, llamadas externas y bytes de salida; traduce errores (sintaxis, tipo, excepción, límite) a texto con línea para que el modelo repare. | `pydantic-monty` |
| `codemode` | `CodeMode(tools, limits)`: arma `search` y `run` neutrales al framework (nombre, descripción, schema, handler async). | catalog, sandbox |
| `trace` | Por `run`: código, cada llamada externa (tool, args resumidos, ms, bytes, error), resultado, límites tocados. Export dict; OpenTelemetry con extra `otel`. | — |
| `adapters/` | `as_tools()` para langchain, pydantic-ai, openai-agents, adk, crewai, llamaindex, smolagents, agent-framework. | extras |
| `mcp_server` | `astromesh-codemode mcp --config upstream.yaml`: servidor MCP que se conecta a N servidores MCP y expone `search` + `run`. | extra `mcp` |
| `eval` | Eval de costo (3.5) y eval de trampas (3.6). | extras |

### 3.3 Semántica

- **Programa:** subconjunto de Python que soporte Monty; `await` en las llamadas a tools; el valor de la
  última expresión o un `return` de nivel superior es el resultado. `print` se captura.
- **Llamadas a tools:** argumentos validados contra el JSON Schema antes de llamar; un error de la tool
  llega al programa como excepción (`ToolError`) con su mensaje, así el programa puede manejarlo.
- **Errores al modelo:** texto corto con tipo, línea y mensaje; nunca un traceback del host.
- **Límites por defecto:** 30 s por `run`, 64 MiB, 50 llamadas a tools, 16 KiB de salida al modelo
  (truncada con aviso). Configurables.
- **Sin estado entre `run`s** en la v0.1: cada `run` arranca limpio.
- **Concurrencia:** llamadas independientes pueden ir en paralelo si Monty lo permite (`gather`);
  si no, en serie. Lo decide el builder según la API de Monty.

### 3.4 Escrituras y compuertas

- La v0.1 es **para lectura**: una fuente puede marcar una tool como `writes=True` y `CodeMode` la
  **excluye del sandbox** por defecto. Para un servidor MCP vivo (fuente `mcp` y proxy), **toda tool
  cuenta como escritura salvo que traiga `readOnlyHint: true`** o figure como lectura en la
  configuración: el error seguro es dejar afuera una tool, no dejar entrar una que escribe.
  *(Decisión del diseñador.)* Se puede incluir con `allow_writes=True` fuera de Astromesh,
  bajo responsabilidad de quien lo configura.
- En Astromesh **nunca**: una tool con compuerta (`confirm`, o una tool mcp que escribe) no puede entrar a
  un grupo `codemode`; el agente queda en draft con el motivo. Sigue disponible como tool directa.

### 3.5 Eval de costo (el que decide si conviene)

- **Escenarios:** la misma tarea resuelta con tool calling directo y con Code Mode, variando el tamaño del
  catálogo (8, 64, 512 tools sintéticas con schemas realistas) y el tamaño de los datos intermedios (chico
  / grande: una tool que devuelve 500 filas de las que hacen falta 3).
- **Nivel 1 (sin modelo):** tokens de contexto que cada estrategia carga (schemas, resultados
  intermedios) con un modelo simulado que sigue un guion. Determinista, corre en CI.
- **Nivel 2 (con modelo):** modelos reales por API (al menos uno barato y uno fuerte); métricas: éxito de
  la tarea, llamadas al modelo, tokens de entrada/salida, costo, latencia. Se publica la tabla con la
  fecha, como el nivel 1 de Context.
- **Regla:** el README dice "conviene a partir de N tools / datos de tamaño X" sólo con lo que mida el
  nivel 2. Si no gana en ningún escenario, se publica igual y se dice.

### 3.6 Eval de seguridad (trampas)

Programas maliciosos con la configuración por defecto: `import os`/`subprocess`, abrir archivos, abrir
red, bucle infinito, bomba de memoria, recursión profunda, llamar una tool que no está en el grupo,
llamar una tool con argumentos fuera del schema, sacar 100 MB por la salida, más llamadas que el tope,
llamar una tool `writes=True` excluida. Éxito: 11/11 detenidas. Corre en CI; una que pase rompe el build.

### 3.7 Empaquetado e identidad

Repo `monaccode/astromesh-codemode`, Apache-2.0, Python ≥3.11 (lo exige Monty). Dependencias base:
`pydantic-monty`. Extras: uno por framework, `mcp`, `otel`, `all`. README + README.es, `docs/`,
`examples/`, `assets/` con logo en la familia Astromesh, CI, PyPI con trusted publishing, versión 0.1.0.

## 4. Integración en Astromesh (fases)

| Fase | Qué | Dónde |
|---|---|---|
| 0 | Librería con los dos evals. **Compuerta dura:** el nivel 2 se corre (claves por API, un modelo barato y uno fuerte) y su tabla se publica **antes** de subir 0.1.0 a PyPI | `astromesh-codemode` |
| 1 | Extra `astromesh[codemode]` y `type: codemode`. Empieza sólo después de la fase 0 publicada | core |
| 2 | Pool de Nexus con el extra; Forge y Cortex editan el bloque; Leia lo conoce; doc-site. **Fuera de este plan**: se planifica aparte cuando 0 y 1 estén cerradas | Nexus, Forge, Cortex, Leia, docs |

**`type: codemode` en el manifiesto (fase 1):**

```yaml
tools:
  - name: crm
    type: mcp
    # … servidor con 120 tools
  - name: crm_code
    type: codemode
    wraps: [crm]            # nombres de otras tools del agente (una mcp agrupa todas sus tools)
    description: "API del CRM: buscá funciones con search y ejecutá un programa con run."
    limits: { timeout: 30, max_calls: 50, max_output_bytes: 16384 }
```

- Las tools envueltas **dejan de exponerse directo** al modelo; quedan detrás de `crm_code_search` y
  `crm_code_run`.
- **Cada llamada desde el programa pasa por el `tool_fn` de la corrida** (`engine.py` ~2261), no directo
  por `ToolRegistry.execute` (que sólo aplica rate limit). Es ahí donde viven permisos, compuerta,
  credenciales por corrida, eventos y spans: el handler de `run` recibe ese `tool_fn` por corrida.
  *(Decisión del diseñador tras la revisión.)*
- **Budget de resultado:** se aplica sólo a la salida final de `run` hacia el modelo. El programa recibe
  el resultado completo de cada tool (si no, el caso "500 filas, hacen falta 3" no existe).
  *(Decisión del diseñador.)*
- **Qué puede ir en `wraps` (v0.1):** `mcp` (sus tools que no escriben), `api`, `builtin` e `integration`
  sin `confirm`. No: `client` (se anuncia pero no se ejecuta), `agent` (abre sub-corridas) ni `a2a`
  (sus tareas pueden durar más que el límite del `run`). *(Decisión del diseñador.)*
- **Permisos:** una tool que `permissions` niega **no entra al catálogo** al construir el agente (no
  aparece en `search`, así el modelo no aprende su nombre) y además se rechaza al llamarla, por si acaso.
  Las dos tools del grupo (`<name>_search`, `<name>_run`) también tienen que estar permitidas.
  *(Decisión del diseñador.)*
- **`origen`:** hoy protege una cosa: un turno con `origen: agente` nunca confirma una tool con
  compuerta. Como ninguna tool con compuerta puede entrar a un grupo `codemode`, Code Mode no abre un
  camino nuevo; el test lo verifica con un turno `agente` que intenta llegar a una tool `confirm`
  desde `run`.
- Sin el extra, `wraps` a una tool inexistente, una tool con compuerta en `wraps`, o claves desconocidas:
  el agente queda en **draft** con el motivo (como `a2a`).
- El uso del modelo no cambia de lugar: la corrida sigue midiéndose igual; el trace del `run` cuelga del
  span de la tool.

## 5. Decisiones

| Decisión | Elegido | Por qué |
|---|---|---|
| Forma | Envoltorio de tools, dos tools (`search`, `run`) | Aditivo, opcional por grupo, mismo molde que Cloudflare/Anthropic; no toca el patrón |
| Lenguaje | Python | El modelo ya lo conoce; un DSL propio fue parte del costo de Glyph |
| Sandbox | Monty, en proceso | Sin contenedor ni latencia de arranque; el código sólo toca lo que le pasamos; MIT |
| Búsqueda | Léxica (BM25) | Sin dependencias ni embeddings; semántica queda para después si el eval la pide |
| Escrituras | Fuera en v0.1; nunca en Astromesh | No abrir un camino para saltarse la compuerta |
| Evidencia | Nivel 2 publicado antes de PyPI y antes del core (compuerta dura) | Lección de Glyph; Context salió con el nivel 2 pendiente y esta vez no |

## 6. Riesgos

- **Monty es joven** (subconjunto de Python, API que cambia): fijar rango de versión; el eval de trampas
  y los tests corren contra la versión fijada.
- **El modelo escribe código que no corre:** cada reparación es otra ida al modelo; el eval lo mide como
  costo, no se esconde.
- **Puede no ganar** en los tamaños que usan nuestros clientes: entonces se publica y queda como opción.
- **Pydantic AI ya trae Code Mode:** nuestro valor es ser neutral al framework, el proxy MCP, el eval y la
  integración con permisos/compuertas/trace de Astromesh.
- **Pool compartido de Nexus:** el sandbox corre en el proceso del runtime; los límites de memoria y
  tiempo son los que protegen al resto de los tenants.

## 7. Lo que queda al builder

Nombres internos, formato exacto de los stubs y del texto de `search`, cómo se mapean tipos de JSON Schema
a anotaciones Python, el diseño de las tareas sintéticas del eval, qué modelos usar en el nivel 2 (uno
barato y uno fuerte), el contenido de los ejemplos y del logo.
