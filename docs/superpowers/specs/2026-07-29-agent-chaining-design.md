# Encadenamiento de agentes (`spec.chain`)

**Fecha:** 2026-07-29
**Estado:** diseño aprobado, pendiente de plan de implementación
**Alcance:** core `astromesh` (`astromesh/chain/`, `astromesh/workflow/`, `astromesh/runtime/`, `astromesh/api/`)

## Problema

Un agente que al terminar dispara otro agente, condicionalmente. Hoy no existe forma
declarativa de expresarlo desde el agente: la única manera es escribir un `kind: Workflow`
aparte que envuelva a los dos.

## Estado del código antes de esta feature

Tres hallazgos condicionan todo el diseño. Los tres se verificaron sobre el árbol en
`develop` a la fecha del spec.

### 1. El motor existe y está completo

`astromesh/workflow/` implementa un orquestador de DAG secuencial con:

- pasos `agent`, `tool`, `switch`, `wait`, `approval`
- plantillas Jinja2 sobre `trigger` y `steps.<n>.output`
- `retry` con backoff fijo o exponencial, `timeout_seconds`, `on_error: <goto>`
- store durable (`store_pg.py`), suspend/resume, aprobación humana
- barrido de runs huérfanos y expirados en `bootstrap()`

Funcionalmente es el equivalente a LangGraph, y nace durable — LangGraph necesita un
checkpointer aparte para eso.

### 2. El motor nunca se instancia fuera de los tests

```
grep -rn "WorkflowEngine" --include="*.py" .
  → astromesh/workflow/__init__.py  (la definición)
  → tests/*                          (7 archivos)
```

`astromesh/api/routes/workflows.py` expone `set_workflow_engine()`, pero **nadie la llama
desde el lifespan de `api/main.py`**. En producción `_engine is None`, así que `GET
/v1/workflows/` devuelve `{"workflows": []}` siempre y ningún workflow corre nunca.

Cablearlo entra en el alcance de esta feature. No es opcional: sin eso no corre ni una
cadena.

### 3. Los agentes no devuelven nada estructurado

`agent.run()` devuelve `{"answer", "steps", "trace"}` (más `plan` o `subtasks` según el
patrón de orquestación). **No hay `data`.**

El workflow de ejemplo versionado en el repo depende de que sí lo haya:

```yaml
# config/workflows/example.workflow.yaml
when: "{{ steps.qualify.output.data.score > 7 }}"
```

Esa condición no puede dar `true` nunca. Y como `StepExecutor` usa `_SilentUndefined`, no
falla: **rinde vacío y cae al `default` en silencio**. Una condición con un typo se comporta
igual que una condición falsa.

Esto es lo que hace que `output_schema` no sea un extra del diseño sino su cimiento: sin
salida estructurada, "bajo ciertas condiciones" no es confiable.

## Decisiones de diseño

| # | Decisión | Alternativa descartada |
|---|---|---|
| 1 | Azúcar en el YAML del agente que **compila a `WorkflowSpec`**; sin motor de ejecución nuevo | Motor de coreografía dirigido por eventos, separado del workflow |
| 2 | `POST /v1/agents/{n}/run` **espera** a la cadena; `answer` sigue siendo la de A y se agrega `chain` | Devolver la `answer` del último eslabón; o fire-and-forget asíncrono |
| 3 | **Disparan todos** los eslabones que matcheen, no sólo el primero | Cascada tipo if/elif (primer match gana) |
| 4 | `mode: sequential \| parallel`, **default `sequential`** | Sólo secuencial; o sólo paralelo |
| 5 | Regla `default: true` que dispara **sólo si ningún `when` matcheó** | Sin válvula de escape |
| 6 | Recursión **con `max_depth` (default 5) y detección de ciclos** | Un solo nivel; o recursión sin techo |
| 7 | Condiciones sobre **`output.data`**, poblado por `spec.output_schema` | Condiciones sobre el texto de `answer`; o condición evaluada por un LLM |
| 8 | `retry`/`timeout_seconds`/`on_error` **por eslabón**, reusando los campos de `StepSpec` | Tolerante (nada corta); o estricto (todo corta) |
| 9 | **Validador mínimo propio**, cero dependencias nuevas | `jsonschema` a deps base; o import opcional |

Las decisiones 1 y 9 comparten una razón: esta feature no debe agregar dependencias de
runtime ni motores paralelos. `api.main` tiene que seguir importando sin extras, porque la
imagen de `astromesh-os` la construye con pip y su boot gate es lo que atrapa un runtime que
importa pero no arranca.

## Superficie YAML

```yaml
apiVersion: astromesh/v1
kind: Agent
metadata:
  name: sales-qualifier

spec:
  # ...identity, model, prompts, orchestration, tools, memory, guardrails...

  output_schema:            # taquigrafía o JSON Schema completo, indistinto
    score:  {type: integer}
    urgent: {type: boolean}

  chain:
    mode: sequential        # sequential | parallel   (default: sequential)
    max_depth: 5            # default: 5

    on_complete:
      - agent: email-composer
        when: "{{ output.data.score > 7 }}"
        input: "{{ output.answer }}"
        retry: {max_attempts: 3, backoff: exponential}
        timeout_seconds: 30
        on_error: continue

      - agent: crm-logger               # sin `when` = dispara siempre

      - agent: triage-humano
        default: true                   # sólo si ningún `when` matcheó
```

### Semántica de las reglas

Para cada regla de `on_complete`, en orden de declaración:

- **con `when`** — se renderiza la plantilla y dispara si el resultado es `true`, `1` o `yes`
  (mismo criterio que `_run_switch` ya usa)
- **sin `when` y sin `default`** — dispara siempre
- **con `default: true`** — dispara sólo si **ninguna regla `when` de esta cadena** dio true.
  Las reglas sin `when` no cuentan como match a estos efectos: en el ejemplo de arriba, con
  `score = 2` disparan `crm-logger` **y** `triage-humano`.

`mode` decide si los eslabones que disparan corren uno tras otro o a la vez. No afecta qué
dispara, sólo cuándo.

**Cuándo se evalúan los `when`.** En `sequential`, cada `when` se evalúa justo antes de
despachar su eslabón, así que puede ver los outputs de los eslabones anteriores vía `steps`.
En `parallel`, **todos los `when` se evalúan de una sola vez antes de arrancar cualquier
eslabón**, contra el output del agente anterior; `steps` no contiene hermanos, porque todavía
no corrió ninguno. Es la consecuencia inevitable de correr en paralelo, y hay que decirla:
una condición que dependa de un hermano funciona en `sequential` y queda siempre falsa en
`parallel`. El compilador **rechaza en bootstrap** un `when` que referencie `steps.<hermano>`
dentro de una cadena `parallel`, nombrando la regla, en vez de dejar que falle callado.

**`input` por defecto.** Un eslabón sin `input` recibe `{{ output.answer }}` — el texto de la
respuesta del agente anterior. Declarar `input` lo sobreescribe.

### Contexto disponible en `when` e `input`

| variable | contenido |
|---|---|
| `output.answer` | texto de la respuesta del agente que acaba de terminar |
| `output.data` | objeto validado contra su `output_schema`, o `None` |
| `output.steps` | pasos de orquestación de ese agente |
| `trigger` | payload original del run (`query`, `session_id`, `context`) |
| `steps` | outputs de todos los eslabones ya ejecutados, por nombre |

`output` siempre refiere al **agente inmediatamente anterior en la cadena**, no a A. En
`A → B → C`, el `when` de la cadena de B ve el `output` de B.

## Arquitectura

### Módulo nuevo: `astromesh/chain/`

| archivo | responsabilidad |
|---|---|
| `models.py` | `ChainSpec`, `ChainLink` — dataclasses, mismo estilo que `workflow/models.py` |
| `compiler.py` | `compile_chain(agent_name, chain_spec, agent_configs) -> WorkflowSpec` |
| `validate.py` | validador mínimo de JSON Schema, sin dependencias |
| `output.py` | extracción y validación de `data` desde la respuesta del agente |

Cada archivo tiene un propósito y se testea solo. `compiler.py` no importa nada del runtime:
recibe los configs de agentes como dato y devuelve un `WorkflowSpec`, lo que lo hace testeable
sin levantar el runtime entero.

### Compilación en bootstrap, no en runtime

Durante el bootstrap del `AgentRuntime`, por cada agente con `spec.chain`:

1. se compila un `WorkflowSpec` sintético llamado `__chain__<agente>`
2. el paso 0 es el agente mismo; los eslabones se agregan detrás
3. las cadenas de los eslabones se **expanden inline**, recursivamente
4. se registra con `WorkflowEngine.register_workflow()`

El prefijo `__chain__` queda **reservado**: `WorkflowLoader` rechaza un workflow escrito a mano
que lo use, porque si no un archivo en `config/workflows/` puede pisar silenciosamente la cadena
compilada de un agente (`register_workflow` reemplaza por nombre, sin avisar).

Compilar en bootstrap y no en runtime da tres cosas:

- **un ciclo, un `max_depth` excedido o un agente inexistente explotan al arrancar**, con la
  ruta completa en el mensaje — no a mitad de una corrida en producción
- el `WorkflowEngine` no necesita saber que las cadenas existen: recibe un `WorkflowSpec`
  normal y lo ejecuta como cualquier otro
- la cadena expandida es **inspeccionable sin ejecutar nada**

**Corrección sobre la estrategia de compilación.** La primera lectura asumía compilar a
`switch` + `goto`. No sirve: en `_drive`, el `goto` de un `switch` ejecuta el paso destino y
**corta el workflow** (`break`). Sirve para ramificar a una rama y terminar, no para "disparan
todos los que matcheen".

La compilación correcta es **un paso por eslabón, con guarda**: se agrega `when: str | None` a
`StepSpec`, evaluado antes de despachar; si da falso el paso devuelve `StepStatus.SKIPPED` y el
run sigue. `SKIPPED` ya está declarado en el enum de `models.py` y no lo usa nadie — la
intención ya estaba, faltaba el mecanismo. Es una adición más chica y más general que
`switch`/`goto`, y le sirve a cualquier workflow escrito a mano.

Esa tercera propiedad es la que diferencia esto de un grafo in-process: la cadena es un
artefacto declarado, versionado en YAML y visualizable, no código que hay que correr para
entender.

### Ejecución

En `POST /v1/agents/{name}/run`:

- **agente sin `chain`** → camino actual, sin tocar. La respuesta es byte-idéntica a la de hoy.
- **agente con `chain`** → se corre `__chain__<name>` en el `WorkflowEngine`;
  `answer`/`data`/`steps`/`trace` salen del paso 0 y el resto arma el bloque `chain`.

### Pieza de motor: `StepType.PARALLEL`

`mode: parallel` requiere fan-out, que el `WorkflowEngine` hoy no tiene. Se agrega:

- `StepType.PARALLEL` en `workflow/models.py`, con un campo `parallel: list[StepSpec]`
- `_run_parallel` en `executor.py`, con `asyncio.gather(..., return_exceptions=True)`
- los outputs se mergean al contexto bajo el nombre de cada sub-step

Los sub-steps son `StepSpec` completos, así que `retry`, `timeout_seconds` y `on_error`
funcionan por rama sin código nuevo. Esto enriquece `kind: Workflow` para todos, no sólo para
cadenas.

### Condiciones estrictas

`StepExecutor` usa `_SilentUndefined`, que es lo que hace que un `when` con typo caiga al
default sin decir nada. Los steps que emite el compilador llevan `strict_conditions: True` y
se renderizan con `StrictUndefined`: un campo inexistente **falla ese eslabón con un mensaje
explícito** en vez de rutear mal en silencio.

Los workflows escritos a mano no cambian de comportamiento — el flag lo pone el compilador,
no el loader.

## `output_schema`

### Declaración

Pasa por `normalize_tool_parameters()` de `astromesh/core/schema.py`, que ya es el punto
canónico donde entra un schema escrito a mano en YAML. Así `output_schema` hereda gratis la
misma taquigrafía que usan los `parameters` de las tools, y quien escriba JSON Schema completo
tampoco es reescrito por detrás.

### Prompt

Ningún provider del repo soporta `response_format` ni `json_schema` (se verificaron los 9 en
`astromesh/providers/`). El `PromptEngine` anexa al system prompt un bloque que pide **prosa
más un bloque ` ```json `** con la forma declarada.

### Parseo

1. se extrae el **último** bloque ` ```json ` de la respuesta
2. si no hay bloque, se intenta parsear la respuesta entera como JSON
3. **`answer` queda intacta, con prosa y todo** — nadie que hoy lea `answer` se rompe
4. `data` se agrega al lado

### Fallo de validación

**No levanta excepción.** `data = None`, se setea `data_error` con el detalle, y queda
registrado en el trace.

Un `when` que referencia `output.data.score` bajo modo estricto falla entonces *ese eslabón*,
con un mensaje que nombra `data_error` como causa raíz.

**Fuera de v1:** reintentar al agente porque emitió JSON inválido. Hacerlo bien exige decidir
si se reintenta la llamada al LLM o el eslabón entero, y eso merece su propia discusión.

## Contrato de respuesta

```json
{
  "answer": "Lead calificado 8/10 — presupuesto confirmado...",
  "data":   {"score": 8, "urgent": true},
  "steps":  [],
  "trace":  {},
  "chain": {
    "run_id": "wf-9c2...",
    "status": "partial",
    "mode": "sequential",
    "links": [
      {"agent": "email-composer", "depth": 1, "via": null,
       "status": "success", "answer": "Enviado a ana@acme.com",
       "data": {"sent": true}, "duration_ms": 812},
      {"agent": "crm-logger", "depth": 1, "via": null,
       "status": "error", "error": "timeout tras 30s"},
      {"agent": "sales-qualifier", "depth": 2, "via": "crm-logger",
       "status": "skipped", "reason": "cycle: ya está en la ruta"}
    ]
  }
}
```

### `chain.status`

| valor | significado |
|---|---|
| `completed` | todos los eslabones que dispararon terminaron bien |
| `partial` | hubo errores pero la cadena siguió (`on_error: continue`) |
| `failed` | un eslabón con `on_error: stop` cortó la cadena |

`answer` y `data` de A se devuelven **siempre**, cualquiera sea `chain.status`. El fallo de un
eslabón nunca invalida la respuesta del agente invocado.

### `chain.links[].status`

| valor | cuándo |
|---|---|
| `success` | el eslabón corrió y terminó bien |
| `error` | corrió y falló; trae `error` con el detalle |
| `skipped` | no corrió; trae `reason` |

**Los eslabones que no dispararon también aparecen en `links`**, con `status: skipped` y
`reason: condition_false`. Es más ruido en la respuesta, pero es la única manera de responder
"¿por qué no se mandó el mail?" sin ir a leer el trace: se ve la regla, se ve que se evaluó y
se ve que dio falso.

`reason` puede ser `condition_false`, `cycle`, `max_depth` o `upstream_stopped` (un eslabón
anterior cortó con `on_error: stop`).

## Observabilidad

### Bug que hay que arreglar

`StepExecutor._run_agent` hace:

```python
session_id = str(uuid.uuid4())
result = await self._runtime.run(step.agent, rendered_input, session_id=session_id)
```

Sesión nueva por paso y **sin `parent_trace_id`**. Tal cual está, cada eslabón abre su propio
árbol de trazas y la cadena es invisible en el timeline.

Los eslabones tienen que heredar `trace_id` y `session_id` del run de A. `AgentRuntime.run()`
ya acepta `parent_trace_id`; falta pasarlo desde el executor. Sin esto, toda la observabilidad
de la feature no existe.

Es un arreglo que beneficia también a los workflows escritos a mano.

### Endpoint de inspección

`GET /v1/agents/{name}/chain` devuelve el grafo ya expandido —agentes, condiciones,
profundidades, ciclos podados. Como es un artefacto de tiempo de compilación, se puede pedir
sin ejecutar nada. Es lo que Forge y Cortex dibujan.

`404` si el agente no declara cadena.

## Cableado

En el lifespan de `astromesh/api/main.py`:

1. instanciar `WorkflowEngine(workflows_dir, runtime, tool_registry, store)`
2. `await engine.bootstrap()`
3. `workflows.set_workflow_engine(engine)`
4. registrar las cadenas compiladas

El store sale de la config existente: `store_pg` si hay Postgres configurado, `InMemoryRunStore`
si no.

## Validador mínimo

`astromesh/chain/validate.py`, sin dependencias:

```python
def validate(data, schema) -> list[str]:
    """Devuelve una lista de errores; vacía significa válido."""
```

**Soporta:** `type` (`object`, `string`, `integer`, `number`, `boolean`, `array`, `null`),
`properties`, `required`, `enum`, `items`.

**Ignora, documentado:** `allOf`, `anyOf`, `oneOf`, `$ref`, `patternProperties`, `format`,
`minimum`, `maximum`, `minLength`, `maxLength`, `pattern`.

Ignorar y no rechazar es deliberado: un `output_schema` con `oneOf` sigue funcionando para las
partes que el validador entiende, en vez de romper el agente entero. La lista de lo ignorado va
en la docstring y en la doc pública.

`jsonschema` es hoy dependencia de dev únicamente. Subirla a base obligaría a `uv lock` en
raíz, `astromesh-node` y `astromesh-cli`, y agregaría una dep al arranque del OS. El
subconjunto de arriba cubre lo que un `output_schema` de agente usa de verdad.

## Manejo de errores

| situación | comportamiento |
|---|---|
| eslabón lanza excepción | aplica `retry`; agotado, se marca `error` y manda `on_error` |
| `on_error: stop` (default) | corta esa rama; en `sequential` no sigue el resto, en `parallel` las otras ramas siguen |
| `on_error: continue` | se registra el error y la cadena sigue |
| `on_error: <agente>` | se salta a ese agente (el `goto` que `StepSpec` ya soporta) |
| timeout de eslabón | igual que excepción; el mensaje nombra el `timeout_seconds` |
| `data` inválida | `data = None` + `data_error`; no corta nada por sí sola |
| ciclo detectado | podado **en compilación**; el link queda `skipped` con `reason: cycle` |
| `max_depth` excedido | `ValueError` en bootstrap, nombrando la ruta completa |
| agente inexistente | `ValueError` en bootstrap, nombrando agente y quién lo referencia |

## Secuencia sugerida

Las piezas se apoyan unas en otras; este es el orden en que cada una queda verificable sola:

1. **Cableado del `WorkflowEngine`** — sin esto nada de lo demás se puede probar end-to-end, y
   es valor inmediato: los workflows escritos a mano empiezan a funcionar por primera vez.
2. **Herencia de trace y sesión** en `StepExecutor._run_agent` — arreglo autónomo que beneficia
   a los workflows existentes.
3. **`output_schema`** (`validate.py` + `output.py` + prompt) — prerequisito de las condiciones;
   entregable por sí solo, ya sirve a workflows a mano.
4. **`StepType.PARALLEL`** — adición al motor, independiente de las cadenas.
5. **`ChainCompiler` + condiciones estrictas** — depende de 3 y 4.
6. **Ruta `/run` y `GET /v1/agents/{n}/chain`** — depende de 1 y 5.

Los pasos 1 a 4 son mejoras reales al motor aunque la feature de cadenas nunca se terminara.

## Plan de tests

TDD: test primero en cada punto.

| archivo | cubre |
|---|---|
| `tests/test_chain_compiler.py` | YAML→`WorkflowSpec`; disparan todos los que matcheen; regla `default`; expansión recursiva; ciclo → `ValueError` con la ruta; `max_depth` excedido; agente inexistente; `mode` default `sequential` |
| `tests/test_workflow_parallel.py` | `StepType.PARALLEL`: `gather`, retry/timeout/`on_error` por rama, merge de contexto, fallo parcial |
| `tests/test_chain_validate.py` | cada tipo soportado; `required`; `enum`; `items`; keywords ignorados no rompen |
| `tests/test_chain_output_schema.py` | taquigrafía normalizada; bloque ` ```json `; JSON pelado; sin bloque → `data=None` + `data_error`; validación fallida; `answer` intacta |
| `tests/test_chain_strict_conditions.py` | `when` con campo inexistente falla el eslabón; los workflows a mano siguen con `_SilentUndefined` |
| `tests/test_chain_api.py` | end-to-end con provider falso; **agente sin `chain` devuelve la forma exacta de hoy** (guarda de regresión); `GET /v1/agents/{n}/chain`; `404` sin cadena |
| `tests/test_chain_trace.py` | un solo árbol de trazas cruzando los eslabones; `session_id` heredado |
| `tests/test_workflow_wiring.py` | `/v1/workflows/` no vacío tras el lifespan |

Los mocks de provider siguen el patrón existente de `tests/conftest.py`; el cliente compartido
ya envuelve la app con `asgi-lifespan`, así que el cableado nuevo se ejercita en cada test de API.

## Fuera de alcance

- reintento del agente ante `output_schema` inválido
- disparo asíncrono fire-and-forget (`chain_run_id` con polling)
- cadenas que crucen nodos vía `PeerClient` — la coreografía distribuida es su propio diseño
- condiciones semánticas evaluadas por un LLM (`when_llm`)
- editor visual de cadenas en Forge; este spec sólo expone el endpoint que lo haría posible

## Documentación

Al terminar la implementación, y no antes:

- `docs/` — sección de encadenamiento con el YAML completo y la tabla de contexto
- `docs-site/` — página pública, sólo una vez que la feature está en un release
- `config/agents/sales-qualifier.agent.yaml` — ejemplo real con `output_schema` y `chain`
- `config/workflows/example.workflow.yaml` — **arreglar** el `when` roto que referencia
  `output.data` sin que exista

## Changelog

`feat:` requiere entrada en `CHANGELOG.md` bajo `[Unreleased]` en el mismo commit o el
inmediatamente anterior, vía la skill `/changelog-automation`.
