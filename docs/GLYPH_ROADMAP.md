# Glyph — hoja de ruta por fases

Glyph es el lenguaje de acción de Astromesh: el modelo emite **un programa** en vez
de N llamadas a tools, y el runtime lo ejecuta encadenando capacidades localmente.
El ahorro viene de eliminar round-trips, no de acortar sintaxis.

- **Diseño:** [`docs/superpowers/specs/2026-08-03-glyph-action-language-design.md`](superpowers/specs/2026-08-03-glyph-action-language-design.md)
- **Plan de v0.1.0:** [`docs/superpowers/plans/2026-08-03-glyph-v0.1.0.md`](superpowers/plans/2026-08-03-glyph-v0.1.0.md)
- **Paquete:** `astromesh-glyph/` (agnóstico — no importa `astromesh`)

## El principio que ordena las fases

El valor de generar un programa en vez de acciones depende de dos variables:
**con qué frecuencia** el modelo genera uno, y **qué tan grandes** son los datos
intermedios que hoy pasan por el contexto.

| Labor | Frecuencia | Datos intermedios | Ahorro | Fase |
|---|---|---|---|---|
| Agente + tools | Altísima | Medianos | Grande y medible hoy | **1** |
| RAG | Alta | Enormes (chunks) | Muy grande en corpus grandes | **2** |
| Coreografía | Baja | Chicos | Bajo — el valor es de producto | **3** |
| ETL | Muy baja | Enormes, pero ya fuera del contexto | Casi nulo | **4** |

Las cuatro fases comparten **la misma gramática**. Lo que cambia entre una y otra
es qué capacidades se exponen al programa, no el lenguaje. Por eso la fase 1 no
elige un dominio: elige el dominio que **fuerza el diseño completo del núcleo**.

---

## Fase 1 — Agente + tools · v0.1.0

**Estado:** implementada — falta la corrida real del benchmark
**Objetivo:** un agente puede declarar `pattern: glyph` y correr, y sabemos con
números cuánto ahorra.

Por qué esta va primero: es el loop más caro y más frecuente del repo, y es el
único caso que obliga a resolver lo difícil — el modelo tiene que anticipar
ramificaciones sin ver los datos, lo que fuerza condicionales y manejo de error de
verdad en el lenguaje. Si Glyph resuelve esto, las otras tres fases se apoyan en
el mismo núcleo sin tocar la gramática.

**Qué entra:**

- Gramática núcleo: asignación, llamada con argumentos por nombre, pipe
  (`where` / `top` / `map`), `if/else`, `return`
- Lexer con bloques por indentación y parser de descenso recursivo
- Compilador a `PlanGraph` — dependencias entre sentencias y validación contra el
  catálogo antes de ejecutar nada
- Executor async por olas topológicas: las sentencias independientes corren
  concurrentes
- `PartialState.to_prompt()` — reparación sin repetir efectos ya aplicados
- `ask` como capacidad de primera clase, para pasos que requieren criterio
- `PatternCapabilities` + `GlyphPattern` + `pattern: glyph` en el core
- Benchmark contra `pattern: react` sobre `autolink-parts` y `support-agent`

**Qué queda afuera a propósito:** bucles, funciones de usuario, imports, recursión.
`map` sobre el pipe cubre la enorme mayoría de los casos, y un `for` abre la puerta
a programas no acotados que habría que limitar por tiempo. Si el benchmark muestra
que hacen falta, entran en v0.2.0 con evidencia detrás.

**Cómo se cierra:** se corre el benchmark contra un proveedor real y sus números se
escriben en el spec. No hay umbral automático de aprobación — la decisión de
avanzar a la fase 2 se toma con los datos delante.

**Lo único pendiente de la fase 1 es esa corrida**, porque gasta dinero real contra
un proveedor. El harness ya está y produce el reporte; falta apretar el botón:

```bash
ASTROMESH_CONFIG_DIR=config uv run python -m bench.glyph.run
```

Una corrida de humo con modelo scripted (tokens simulados, ejecución real) ya
confirma la parte estructural: en `support-agent` la ejecución tarda 305 ms contra
454 ms de ReAct, porque `find_order` y `refund_policy` caen en la misma ola del DAG
y ReAct las hace en serie por construcción. Lo que falta medir de verdad son los
tokens y la tasa de programas inválidos, que son las dos incógnitas del proyecto.

**Qué mirar en esos números:**

| Señal | Qué significa | Dónde se arregla |
|---|---|---|
| Tasa alta de programas inválidos | La apuesta de la sintaxis familiar falla | `prompt/grammar.py`, mensajes del compilador |
| Ahorro bajo con correctitud igual | El bloque de gramática infla demasiado el prompt | acortar `GRAMMAR` |
| Correctitud peor que ReAct | El modelo no puede ramificar a ciegas en estos casos | más uso de `ask`, o bucles en v0.2.0 |
| Latencia sin mejora | Los programas no tienen sentencias independientes | revisar los escenarios, no el motor |

---

## Fase 2 — RAG + pushdown de pipes

**Depende de:** fase 1 con el benchmark publicado.

El pack de RAG expone `retrieve`, `rerank` y `summarize` como capacidades, y el
programa las encadena:

```glyph
d = retrieve("política de devoluciones", k=40)
    | where(score > 0.75) | rerank(model="bge") | top(5)
return ask("resumí plazos y excepciones", context=d)
```

Lo que hace valiosa a esta fase no es el pack — es el **pushdown**. Hoy el pipe
filtra en memoria: `retrieve(k=40)` trae 40 chunks y `where` descarta 35. Con
pushdown, el compilador reconoce que `where(score > 0.75) | top(5)` es traducible a
la query del store y trae 5. Los 35 chunks descartados nunca se materializan ni
entran al contexto.

La gramática de v0.1.0 ya lo habilita: el pipe es declarativo justamente por esto.
Una comprensión de lista al estilo Python obligaría a materializar las 40 primero, y
por eso el pipe es la única construcción no-familiar que el lenguaje se permite.

**Un asterisco honesto:** el pipeline de retrieval+rerank de Astromesh ya es
configuración, no decisión del modelo. Esta fase agrega valor donde la consulta
necesita un pipeline **distinto** cada vez. Si en la práctica el 90% de las
consultas usan el mismo pipeline, el ahorro ya está capturado por la configuración
y esta fase vale menos de lo que parece. Es lo primero a verificar antes de
empezarla.

**Alcance previsto:** pack de capacidades RAG, pushdown de `where`/`top` al store,
métricas de chunks materializados vs. traídos, extensión del benchmark con un
escenario de corpus grande.

---

## Fase 3 — Coreografía dinámica

**Depende de:** fase 2, y de una decisión explícita de avanzar.

Que el agente escriba su propia cadena en runtime, en vez de tenerla fija en
`spec.chain` del YAML:

```glyph
r = agent.sales_qualifier(lead)
if r.score >= 8:
    agent.email_composer(lead, tone="warm")
else:
    crm.tag(lead, "cold")
```

**Es el mejor diferenciador del ecosistema y el peor vehículo para ahorrar
tokens.** Se genera pocas veces y mueve datos chicos; el ahorro es de densidad de
output (un `WorkflowSpec` en YAML cuesta varias veces más tokens que estas cuatro
líneas, y los tokens de salida son los caros), no de round-trips eliminados. Va
tercera por eso: el diferencial se apoya sobre un lenguaje ya medido, no sobre una
apuesta.

El puente técnico ya está construido sin haberlo buscado: un `PlanGraph` es un DAG,
y `WorkflowSpec` (`astromesh/workflow/models.py`) también. Mapear uno al otro le da
a un programa Glyph la durabilidad, el suspend/resume y la aprobación humana que el
motor de workflow ya tiene. Ese mapeo vive en el adapter del core, **no** en el
núcleo agnóstico.

**Lo que hay que resolver antes:** permisos. Un programa que elige qué agentes
invocar es un LLM decidiendo a quién llamar. El catálogo de capacidades tiene que
declarar qué agentes puede alcanzar cada agente, con el mismo rigor que hoy tienen
los permisos de tools.

**Alcance previsto:** pack de capacidades `agent.*`, mapeo `PlanGraph` →
`WorkflowSpec`, permisos de invocación entre agentes, durabilidad de programas
largos.

---

## Fase 4 — ETL / integraciones

**Depende de:** fase 3.

Pipelines sobre el catálogo de `astromesh/integrations/`:

```glyph
rows = hubspot.contacts(updated_since="7d")
       | map({email, name: full_name}) | where(email != null)
postgres.upsert("contacts", rows, key="email")
```

Es la fase de mayor valor de producto y menor ahorro de tokens: un pipeline ETL se
escribe una vez y vive meses, así que el modelo casi nunca lo genera. Va última
porque no justifica un lenguaje por sí sola — lo aprovecha una vez que existe.

**Alcance previsto:** pack de capacidades sobre el catálogo de integraciones,
manejo de volúmenes que no entran en memoria, programación de corridas.

---

## Lo que no cambia entre fases

Tres compromisos que sostienen todo el diseño y que ninguna fase puede romper:

1. **El núcleo no importa `astromesh`.** Glyph tiene que poder adoptarse fuera del
   ecosistema; la frontera limpia es lo que fuerza que el diseño sea bueno. Todo lo
   específico de Astromesh vive en el adapter del core.
2. **`astromesh` depende de `astromesh-glyph` como extra opcional, nunca base.**
   `astromesh/api/main.py` tiene que seguir importando sin extras o la imagen de
   `astromesh-os` no bootea.
3. **El bloque de gramática se mantiene chico.** Es el único costo fijo por turno
   que agrega Glyph y compite directamente con el ahorro que produce. Hay un test
   que lo limita; si crece, se acorta el texto — no se sube el umbral.
