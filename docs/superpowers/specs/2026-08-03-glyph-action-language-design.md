# Glyph — lenguaje de acción para agentes (`astromesh-glyph`)

**Fecha:** 2026-08-03
**Estado:** diseño aprobado, pendiente de plan de implementación
**Alcance:** repo nuevo `astromesh-glyph` (agnóstico) + integración en el core (`astromesh/orchestration/`, `astromesh/runtime/engine.py`)

## Problema

Un agente con tools gasta la mayor parte de sus tokens en **vueltas**, no en contenido.

El loop ReAct (`astromesh/orchestration/patterns.py:35`) llama al modelo una vez por tool.
Cada llamada reenvía el system prompt, los schemas de todas las tools y el historial
acumulado hasta ese punto. Un agente como `autolink-parts` que busca, filtra, cotiza y
agenda hace 4-6 iteraciones: el mismo contexto viaja 4-6 veces, creciendo en cada una.

Además el loop es **secuencial por construcción**. Dos tools que no dependen entre sí
—buscar repuestos OEM y buscar alternativos— se ejecutan una después de la otra porque
el patrón sólo puede pedir una acción por vuelta.

La hipótesis de este diseño: si el modelo emite **un programa** en vez de N acciones, el
runtime lo ejecuta localmente encadenando tools sin volver al LLM, y devuelve sólo el
resultado. El ahorro viene de eliminar round-trips, no de acortar sintaxis.

## Qué NO es esto

Descartado explícitamente durante el brainstorming, porque es la trampa obvia de la idea:

**Glyph no es una sintaxis comprimida.** Inventar notación densa (símbolos cortos, menos
separadores) ahorra ~15% de tokens de salida y cuesta precisión, porque el modelo nunca vio
esa sintaxis. Un programa que no parsea cuesta un round-trip de reparación — justamente lo
que el lenguaje vino a eliminar. Con 10% de tasa de error de sintaxis, el margen se evapora
entero. La superficie de Glyph es deliberadamente **familiar**.

## Decisiones de diseño

| # | Decisión | Alternativa descartada |
|---|---|---|
| 1 | Lenguaje de **acción** que el LLM emite y el runtime ejecuta | Formato compacto de datos/schemas; DSL para *definir* agentes |
| 2 | Sintaxis **familiar** (estructura tipo Python) + pipe declarativo | Notación densa propia; Python restringido validado por AST |
| 3 | Repo **agnóstico**: `astromesh-glyph` no importa `astromesh` | Acoplado al core; o núcleo agnóstico + pack oficial en el mismo repo |
| 4 | Hay **fase de compilación**, y su producto es un DAG de ejecución | Intérprete puro sobre el AST |
| 5 | Fallo → **cortar y devolver al LLM** con estado parcial | Saga con compensaciones; o tools clasificadas lectura/escritura |
| 6 | `ask(...)` es capacidad de primera clase | Sin escape semántico: cortar el programa para cualquier razonamiento |
| 7 | **Sin loops** ni funciones de usuario en v0.1.0 | Gramática completa desde el principio |
| 8 | Primera labor: **agente + tools**; RAG, coreografía y ETL son packs posteriores | Empezar por coreografía dinámica |
| 9 | Benchmark obligatorio, **sin umbral fijo** de aprobación | Gate automático (−40% o −60% de tokens) |

Las decisiones 2 y 4 comparten razón: la precisión del modelo vale más que la densidad, y
todo lo que se pueda detectar sin ejecutar hay que detectarlo sin ejecutar.

### Por qué la decisión 8 va contra la intuición

La coreografía dinámica —que el agente escriba su propia cadena en runtime— es el mejor
diferenciador del ecosistema, pero el **peor** vehículo para ahorrar tokens: se genera pocas
veces y mueve datos chicos. El ahorro depende de *frecuencia de generación* × *tamaño de los
datos intermedios*:

| Labor | Frecuencia | Datos intermedios | Ahorro esperado |
|---|---|---|---|
| Agente + tools | Altísima (cada conversación) | Medianos | Grande, y medible hoy |
| RAG | Alta (cada consulta) | Enormes (chunks) | Muy grande en corpus grandes |
| Coreografía | Baja (se escribe una vez) | Chicos | Bajo — el valor es de producto |
| ETL | Muy baja (pipeline estable) | Enormes, pero ya no pasan por el contexto | Casi nulo |

Agente+tools es además el caso que **fuerza el diseño completo del núcleo**: el modelo tiene
que anticipar ramificaciones sin ver los datos, lo que obliga a condicionales y manejo de
error de verdad. Si el lenguaje resuelve esto, los otros tres packs salen encima sin cambiar
la gramática.

## La superficie del lenguaje

```
v = search_parts(make="Toyota", model="Corolla",
                 year=2019, part="pastillas")

oem = v | where(kind == "oem") | top(3, by=rating)
alt = v | where(kind == "aftermarket", stock > 0)
          | top(3, by=price)

if oem.empty:
    eta = check_restock(v.first.sku)

return {oem, alt, eta}
```

Cinco construcciones y nada más: asignación, llamada con kwargs, pipe, `if/else`, `return`.

Dos aclaraciones de gramática que el ejemplo deja implícitas:

- `{oem, alt, eta}` es un **dict con claves inferidas** del nombre de la variable —
  equivale a `{"oem": oem, "alt": alt, "eta": eta}`. No hay literal de set en el lenguaje.
- Varios argumentos en un `where(...)` se combinan con **AND**: `where(kind == "oem",
  stock > 0)` filtra por ambas. No hay `or` implícito.

El **pipe** es la única construcción no-Python, y no entra por densidad sino por capacidad.
`retrieve(...) | where(score > 0.75) | top(5)` es declarativo: el runtime puede empujar el
filtro al store y traer 5 filas en vez de 40. Una comprensión de lista obliga a materializar
las 40 primero. (El pushdown en sí es fase 2 — la gramática lo habilita desde v0.1.0.)

Los mismos cinco constructos cubren los cuatro dominios; lo que cambia entre packs es qué
capacidades se exponen, no la gramática:

```
# RAG
d = retrieve("política de devoluciones", k=40) | where(score > 0.75) | rerank(model="bge") | top(5)
return ask("resumí plazos y excepciones", context=d)

# Coreografía
r = agent.sales_qualifier(lead)
if r.score >= 8:
    agent.email_composer(lead, tone="warm")
else:
    crm.tag(lead, "cold")

# ETL
rows = hubspot.contacts(updated_since="7d") | map({email, name: full_name}) | where(email != null)
postgres.upsert("contacts", rows, key="email")
```

## Arquitectura

Repo `astromesh-glyph`, cuatro capas, sin dependencia de `astromesh`:

- **`glyph/syntax/`** — lexer + parser → AST. Gramática cerrada. Sin `eval`, sin Turing
  completo, sin imports.
- **`glyph/plan/`** — el compilador: AST → `PlanGraph`, un grafo de dependencias entre
  variables con nodos condicionales. Resuelve qué puede correr concurrente y valida contra el
  catálogo de capacidades (existe, aridad, tipos donde se pueda).
- **`glyph/runtime/`** — ejecutor async del `PlanGraph` contra un `CapabilityProvider`.
  Concurrencia, timeout por nodo, captura de estado parcial al fallar.
- **`glyph/prompt/`** — genera el bloque de sistema que le enseña Glyph al modelo: gramática
  mínima + catálogo de capacidades.

### La frontera

```python
@runtime_checkable
class CapabilityProvider(Protocol):
    def list_capabilities(self) -> list[CapabilitySpec]: ...
    async def invoke(self, name: str, args: dict) -> Any: ...
```

Dos métodos. Mismo idioma que `ProviderProtocol` (`astromesh/providers/base.py:62`), que ya
es un `Protocol` runtime-checkable en este repo.

`CapabilitySpec` lleva `name`, `description`, `parameters` (JSON Schema) y un flag
`is_semantic` que marca las capacidades que invocan un modelo — necesario para contabilizar
round-trips en el benchmark.

### Por qué compilar

Parsear 95 tokens son microsegundos y el tiempo real de un programa lo domina el I/O; el
compilador no existe para acelerar instrucciones. Existe por dos razones:

1. **Concurrencia.** `oem` y `alt` del ejemplo no dependen entre sí; el `PlanGraph` las corre
   en paralelo. ReAct no puede hacerlo nunca. Esto baja la latencia por un factor distinto y
   multiplicativo respecto del ahorro de tokens.
2. **Fallar antes de gastar.** Una capacidad inexistente o un argumento que no matchea se
   detectan sin ejecutar nada, y el error vuelve al modelo con el mensaje exacto. Un
   intérprete puro lo descubriría a mitad de camino, con efectos ya hechos.

Consecuencia útil para la fase 3: un `PlanGraph` es un DAG, y `WorkflowSpec`
(`astromesh/workflow/models.py`) también. La coreografía dinámica sale de mapear uno al otro
—en el adapter del core, no en el núcleo agnóstico.

### Integración en el core

Menos invasiva de lo esperado, porque la interfaz de patrones ya encaja:

```python
# astromesh/orchestration/patterns.py:28
async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10) -> dict
```

`tool_fn(name, args)` (`astromesh/runtime/engine.py:939`) tiene exactamente la forma de
`CapabilityProvider.invoke`, y `tools` ya son los schemas de función que necesita
`list_capabilities()`. El adapter `ToolRegistryCapabilities` es un envoltorio delgado sobre
ambos, heredando permisos, rate limits y `requires_approval` que ya viven en `ToolRegistry`
sin duplicarlos.

Cambios en el core:

1. `GlyphPattern(OrchestrationPattern)` nuevo, en `astromesh/orchestration/glyph_pattern.py`.
2. Una entrada `"glyph": GlyphPattern` en el `pattern_map` de `engine.py:603`.
3. `astromesh-glyph` como **extra opcional** — `api.main` tiene que seguir importando sin
   extras (restricción de la imagen de `astromesh-os`), así que el import va dentro de la
   rama que construye el patrón, no en el módulo.

Nada más. Los agentes lo activan con `spec.orchestration.pattern: glyph`.

## Flujo de ejecución

```
query
  → prompt (gramática + catálogo de capacidades)
  → el LLM emite un .glyph
  → parse          ─┐ error acá: vuelve al modelo
  → compile        ─┘ sin haber ejecutado nada
  → ejecutar PlanGraph (nodos independientes en paralelo)
  → resultado
  → el LLM redacta la respuesta final
```

Dos llamadas al modelo en el caso feliz, contra las 6-7 de ReAct.

`GlyphPattern.execute()` devuelve el mismo `dict` que los demás patrones —con `steps` como
lista de `AgentStep`, un nodo del plan por step— para que el tracing, la contabilidad de uso
(`astromesh/api/usage.py`) y los eventos de WebSocket sigan funcionando sin cambios.

## El primitivo `ask`

`ask(prompt, context=...)` invoca al modelo dentro del programa. Es la válvula para pasos
semánticos: resumir, clasificar un tono, decidir con criterio. Sin esto, cualquier
razonamiento obliga a cortar el programa y volver, y el pack de RAG directamente no existe.

La contrapartida es explícita: cada `ask` es un round-trip que el programa **eligió** pagar.
El benchmark los contabiliza aparte de los round-trips de reparación, porque son gasto útil,
no desperdicio.

## Manejo de errores

Un fallo en el nodo N corta la ejecución. El runtime serializa:

- las variables ya ligadas, con sus valores
- qué nodos se ejecutaron y cuáles no
- el error, con el nombre de la capacidad y los argumentos que recibió

Eso vuelve al LLM, que emite un programa nuevo continuando desde ahí. El prompt de
reparación dice explícitamente qué efectos ya ocurrieron y que no los repita.

Sin transacciones ni compensaciones: exigir que todo el catálogo de tools declare su
operación inversa es mucho trabajo y muchas no tienen inversa real. La contrapartida se
asume: los efectos de los nodos 1..N-1 quedan hechos, y el modelo tiene que saberlo.

## Testing

- **Parser** — property-based (Hypothesis): todo AST válido serializa y re-parsea idéntico.
- **Compilador** — casos de dependencias con el `PlanGraph` esperado; errores de compilación
  con los mensajes exactos verificados, porque esos mensajes son la interfaz de reparación
  con el modelo y un mensaje malo cuesta round-trips.
- **Runtime** — capabilities mockeadas deterministas; tests de concurrencia real (dos nodos
  independientes corren solapados) y de fallo parcial (el estado serializado es correcto).
- **Integración (core)** — `GlyphPattern` contra un `ToolRegistry` real con tools mockeadas;
  verificar que permisos y rate limits siguen aplicando a través del adapter.

### Benchmark

Harness aparte en `bench/`, corriendo `pattern: glyph` contra `pattern: react` sobre
`autolink-parts` y `support-agent`, mismo modelo y mismas tools mockeadas deterministas.

Métricas publicadas por corrida:

| Métrica | Por qué |
|---|---|
| Tokens de entrada / salida | El objetivo primario |
| Round-trips al modelo | La causa del ahorro; separando `ask` de reparación |
| Latencia wall-clock | Captura la ganancia de concurrencia, invisible en tokens |
| Correctitud de la tarea | Sin esto el ahorro no significa nada |
| Tasa de programas inválidos | Valida o refuta la apuesta de la decisión 2 |

Corre nightly en CI, no en el gate de PR: gasta dinero real.

**No hay umbral automático de aprobación.** Los números se publican y la decisión de avanzar
a la fase 3 se toma con los datos en la mano.

## Alcance de v0.1.0

**Entra:**

- Gramática núcleo: asignación, llamada con kwargs, pipe, `if/else`, `return`, literales,
  dict, list, acceso por atributo
- Compilador con planificación de concurrencia y validación contra el catálogo
- Runtime async con timeout por nodo y estado parcial en fallo
- `ask` como capacidad de primera clase
- Capability pack de tools vía `ToolRegistryCapabilities`
- `GlyphPattern` y su entrada en `pattern_map`
- Benchmark

**Queda afuera, deliberadamente:**

- Loops, funciones de usuario, imports, recursión
- Pushdown de pipes al store — fase 2, con el pack de RAG
- Durabilidad y mapeo a `WorkflowSpec` — fase 3, con coreografía
- Packs de RAG, coreografía y ETL

Sin loops es la decisión más discutible del alcance y se sostiene: `map` sobre el pipe cubre
la enorme mayoría de los casos, y un `for` abre la puerta a programas no acotados que hay que
limitar por tiempo de ejecución. Si el benchmark muestra que hacen falta, entran en v0.2.0
con evidencia detrás.

## Fases posteriores

| Fase | Contenido | Depende de |
|---|---|---|
| 2 | Pack de RAG + pushdown de pipes al store | v0.1.0 con benchmark publicado |
| 3 | Coreografía dinámica: `PlanGraph` → `WorkflowSpec`, durabilidad, permisos sobre qué agentes puede invocar un programa | Fase 2, y la decisión explícita de avanzar |
| 4 | Pack de ETL sobre el catálogo de `astromesh/integrations/` | Fase 3 |

## Resultados del benchmark — primera corrida (2026-08-03)

Modelo `kimi-k2.5` vía Moonshot, tools mockeadas deterministas, `pattern: glyph`
contra `pattern: react`.

| | ReAct | Glyph | Δ |
|---|---:|---:|---:|
| **autolink-parts** — tokens totales | 1.143 | 10.736 | +839% |
| llamadas al modelo | 2 | 3 | +50% |
| latencia | 20,0 s | 227,6 s | +1040% |
| respuesta correcta | sí | **no** | |
| programas inválidos | — | **2** | |
| **support-agent** — tokens totales | 1.031 | 3.267 | +217% |
| llamadas al modelo | 2 | 3 | +50% |
| latencia | 10,5 s | 41,4 s | +295% |
| respuesta correcta | sí | sí | |
| programas inválidos | — | 0 | |

**Glyph perdió en las dos, y en una falló del todo.** El diagnóstico es preciso y
no absuelve al lenguaje, pero tampoco confirma que la hipótesis esté mal: los
números están dominados por dos bugs de implementación y dos confusiones de
medición, ninguno de los cuales es la apuesta que el benchmark venía a evaluar.

### Bug 1 — el parser rechaza todo lo multilínea

El modelo escribió un programa idiomático y legible, con un `return` de un dict
anidado repartido en varias líneas. El parser lo rechazó:

```
GlyphSyntaxError: línea 16, columna 9: se esperaba NAME y se encontró '\n'
```

Verificado después contra el parser local: **falla cualquier** construcción
multilínea entre paréntesis o llaves — dict, llamada y lista. Python permite
continuación implícita dentro de corchetes; Glyph decía tener sintaxis familiar y
no la tiene. Es el bug que causó los 2 programas inválidos y el fallo total del
escenario.

Es un error de diseño del lexer, no un descuido: emite `NEWLINE` sin llevar cuenta
de la profundidad de corchetes abiertos.

### Bug 2 — el catálogo describe las entradas, no las salidas

El programa filtraba por `where(is_oem == true)` y leía `.brand`, `.description`,
`.relevance`. Ninguno de esos campos existe en los datos. `build_system_block()`
publica el JSON Schema de los **parámetros** de cada capacidad y nada sobre la
**forma de lo que devuelve**, así que el modelo tiene que inventar los nombres de
campo — y en un lenguaje donde el pipe filtra por campo, inventarlos produce
colecciones vacías en silencio.

Con el bug 1 arreglado, este programa habría compilado y ejecutado, devolviendo
resultados vacíos. Peor que un error: un fallo silencioso.

### Confusión 1 — el modelo es de razonamiento

`kimi-k2.5` emite chain-of-thought, y esa cadena cuenta como tokens de salida:
8.148 contra 601 de ReAct en autolink. Pedirle un programa en un lenguaje que
nunca vio dispara mucho más razonamiento que pedirle una tool call. Parte del
+839% es eso, no el lenguaje. Hay que medir también contra un modelo sin
razonamiento explícito para separar las dos cosas.

### Confusión 2 — ReAct no hizo el loop que el diseño ataca

ReAct resolvió los escenarios con 2 llamadas y 1-2 tools. La hipótesis apunta a un
loop de 4-6 iteraciones; contra un ReAct de 2 llamadas no hay round-trips que
eliminar y Glyph sólo puede perder. Los escenarios son demasiado fáciles: hay que
construir alguno que fuerce el encadenamiento largo que Glyph viene a colapsar.

### Qué se concluye

El benchmark hizo exactamente su trabajo en la primera corrida: encontró que la
premisa central —"sintaxis familiar, el modelo la escribe bien"— está mal
implementada, no mal elegida. El modelo escribió Glyph correcto; el parser no
aceptaba Glyph correcto.

La apuesta sigue sin evaluarse. Para evaluarla hace falta, en orden: continuación
de línea dentro de corchetes, forma de salida en el catálogo, un escenario con
encadenamiento largo, y una segunda corrida contra un modelo sin razonamiento.

## Resultados del benchmark — segunda corrida (2026-08-03)

Con los cuatro arreglos aplicados: continuación de línea entre corchetes, `returns`
en el catálogo, un escenario de cadena larga, y un segundo modelo sin razonamiento.

### `kimi-k2.5` (razonamiento)

| escenario | tokens ReAct | tokens Glyph | Δ | correcta | inválidos |
|---|---:|---:|---:|:---:|---:|
| autolink-parts | 1.174 | 5.982 | +410% | sí / **sí** | **0** |
| support-agent | 1.035 | 3.479 | +236% | sí / sí | 0 |
| cadena larga | 3.894 | 15.235 | +291% | no / no | 2 |

### `moonshot-v1-32k` (sin razonamiento)

| escenario | tokens ReAct | tokens Glyph | Δ | correcta | inválidos |
|---|---:|---:|---:|:---:|---:|
| autolink-parts | 1.574 | 3.551 | +126% | sí / no | 2 |
| support-agent | 924 | 2.626 | +184% | sí / no | 2 |
| cadena larga | 3.001 | 4.101 | +37% | no / no | 2 |

**Los arreglos funcionaron**: con `kimi-k2.5`, autolink pasó de fallar entero a
responder bien con **cero programas inválidos**. La apuesta de la sintaxis
familiar se sostiene cuando el parser efectivamente acepta sintaxis familiar.

**Y aun así Glyph pierde en tokens en las seis mediciones.** El motivo no es el
que el diseño anticipaba.

### Hallazgo central — la premisa del spec es falsa

El planteo del problema dice: *"El loop ReAct llama al modelo una vez por tool."*
Medido sobre el escenario de cadena larga con `kimi-k2.5`, las tool calls emitidas
por respuesta fueron:

```
[1, 2, 2, 1, 0]   →   6 tools en 5 llamadas al modelo
```

**ReAct ya paraleliza.** `ReActPattern` itera sobre `response.tool_calls`, en
plural, y los modelos modernos emiten varias tools independientes en una sola
respuesta. No hay 6 round-trips que eliminar: hay 5, y Glyph gasta 4.

El ahorro que justificaba el proyecto —eliminar vueltas— ya estaba capturado por
el parallel tool calling del proveedor. Lo que Glyph agrega encima es marginal, y
lo paga caro:

| Costo | Magnitud medida |
|---|---|
| Bloque de gramática en cada prompt | +900 a +2.200 tokens de entrada |
| El modelo escribiendo un programa | 4.362 tokens de salida contra 615 de ReAct |

El segundo costo es el que decide, y sorprende: escribir un programa en un
lenguaje que el modelo nunca vio le cuesta mucho más razonamiento que emitir tool
calls, que sí vio millones de veces. Con `moonshot-v1-32k` la brecha se achica
(+126% en vez de +410%) pero no se da vuelta, y ese modelo además no logra
escribir Glyph válido.

### Modos de fallo que quedan abiertos

`moonshot-v1-32k` falló los tres escenarios. Los programas son estructuralmente
correctos —el modelo entendió el lenguaje— y lo que rompe es superficie:

1. **Claves de dict entre comillas**: `return {"oem": x}`. El parser sólo acepta
   identificadores pelados. Misma clase de bug que el multilínea.
2. **Literales de Python**: `ticket = None` en vez de `null`.
3. **Llamada a capacidad dentro de `map`**: `active | map({g: warranty(sku=sku)})`.

El tercero refuta la **decisión 7** y su defensa en el plan (*"`map` sobre el pipe
cubre el 95% de los casos"*). No los cubre: el uso natural de `map` es "corré esta
tool por cada ítem", lo pidieron los dos modelos, y Glyph no puede expresarlo. Los
stages se evalúan sincrónicos a propósito y no pueden invocar capacidades.

### Qué se concluye

**La tesis de ahorro de tokens para el caso agente+tools no se sostiene**, y no por
un defecto de implementación sino porque el problema que atacaba ya estaba
resuelto por otro lado. Arreglar los tres modos de fallo restantes mejoraría la
tasa de programas válidos, no el balance de tokens: el costo está en la gramática
en el prompt y en el razonamiento de escritura, y ninguno de los dos se va con más
parser.

Lo que sigue teniendo valor, y no fue medido acá:

- **Ramificar sin round-trip.** Un `if` sobre datos que ReAct sólo puede resolver
  volviendo al modelo. Los escenarios usados tienen ramas triviales.
- **Datos que no entran al contexto.** Es el corazón de la fase 2 (RAG): acá los
  resultados de las tools son de tres filas y no hay nada que ahorrar. Con 40
  chunks la aritmética es otra.
- **Coreografía declarativa** (fase 3), cuyo valor siempre fue de producto y no de
  tokens.

La decisión de seguir, y con qué alcance, queda abierta con estos números a la
vista.

## Riesgos

**El modelo escribe Glyph mal.** Es el riesgo central y la razón de la decisión 2. Lo mide
directamente la tasa de programas inválidos del benchmark. Si es alta con sintaxis familiar,
la hipótesis del proyecto está mal y hay que saberlo temprano — por eso el benchmark es parte
de v0.1.0 y no de después.

**El bloque de gramática infla el prompt.** Es el único costo fijo por turno que agrega
Glyph, y compite directamente con el ahorro. Hay que mantenerlo chico y medirlo como parte de
los tokens de entrada, no aparte.

**Ramificación a ciegas.** El modelo escribe el programa sin ver los datos. Si la decisión
requiere mirar un resultado intermedio con criterio semántico, el programa tiene que usar
`ask` (round-trip elegido) o cortar. Cuánto pasa esto en la práctica lo dice el benchmark.
