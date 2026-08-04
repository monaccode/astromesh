# Glyph como lenguaje de autoría: `spec.program`

**Fecha:** 2026-08-04
**Estado:** diseño aprobado, pendiente de plan de implementación
**Alcance:** `astromesh/orchestration/glyph_pattern.py`, `astromesh/runtime/engine.py`, docs

## El problema, medido

Glyph como patrón de runtime pierde contra ReAct en las cuatro métricas que
importan. Medido sobre `kimi-k2.7-code-highspeed`
(`bench/glyph/results-2026-08-04-con-cache.md`):

| | ReAct | Glyph |
|---|---:|---:|
| Costo | 0,00623 USD | **0,03226 USD (+418%)** |
| Latencia | 9,1 s | **44,5 s (+389%)** |
| Tokens totales | 5.367 | 9.232 (+72%) |

**El 98% de ese costo es una sola cosa: el modelo escribiendo el programa.** 7.920
tokens de salida, a 4,2x el precio de los de entrada.

Y lo reescribe **en cada corrida**, idéntico, para la misma tarea. Ahí está toda la
pérdida, y ahí está la salida.

### El error de diseño original

El planteo era: *que el modelo emita un programa en vez de N acciones, para gastar
menos*. Pero generar un programa es lo más caro y lo más lento que hace un LLM por
unidad de valor. **El diseño puso al modelo a trabajar más, no menos.**

La inversión correcta: **el modelo como autor, no como intérprete.** Escribe el
artefacto una vez —donde su inteligencia aporta de verdad— y después no participa.

### Lo que sí se salvó

Una cosa aguantó todas las corridas: en la cadena de seis tools, **ReAct acierta
1 de 5 veces y Glyph 3 de 5**. ReAct tiene que sostener un plan de seis pasos a
través de cinco llamadas, redescubriéndolo del transcript cada vez. Un programa se
escribe entero de una y el compilador lo valida antes de ejecutar nada.

Esa ventaja de confiabilidad **se conserva intacta** con el programa fijo, y pasa a
costar casi nada.

## Qué se construye

Un agente puede declarar su programa Glyph en el YAML. El patrón lo ejecuta
directamente, sin pedirle nada al modelo.

```yaml
spec:
  orchestration:
    pattern: glyph
    narrate: false
  program: |
    orden = find_order(order_id=context.order_id)
    politica = refund_policy()
    if orden.days_since < politica.window_days:
        ticket = open_ticket(order_id=context.order_id)
    return {orden, politica, ticket}
```

### La economía

| configuración | costo/corrida | vs ReAct |
|---|---:|---:|
| ReAct | 0,00623 | — |
| Glyph generando (hoy) | 0,03226 | +418% |
| `spec.program`, sin `ask` | **0,00000** | **−100%** |
| `spec.program` + un `ask` de extracción | ~0,0006 | ~−90% |

Sin `ask` y con `narrate: false`, una corrida hace **cero llamadas al modelo**:
cuesta nada y tarda lo que tarden las tools, ejecutadas en paralelo por el DAG.

## Decisiones de diseño

| # | Decisión | Alternativa descartada |
|---|---|---|
| 1 | Programa **fijo por agente** en el YAML | Caché por forma de consulta (queda para después) |
| 2 | **Fallar explícito** si el programa no cubre la consulta | Caer a generar; o caer a `react` |
| 3 | Validación **en el bootstrap**, no en la primera consulta | Compilar perezosamente al primer request |
| 4 | El programa lee `query` y `context` | Sólo `query`, con `ask()` para todo |
| 5 | El patrón **expone el programa que generó**, para poder fijarlo | Un comando aparte que genere programas |

### Por qué la decisión 2

Un programa fijo es un contrato. Si no cubre la consulta, el agente devuelve error.

Caer a generar traería el costo de vuelta justo cuando menos se lo espera y de
forma imposible de presupuestar. Caer a `react` mezclaría dos modos con costos que
difieren 400x bajo un mismo agente.

Además, el fallo silencioso es exactamente el defecto que el motor de workflow ya
tiene: `StepExecutor` usa `_SilentUndefined`, así que **una condición con un typo
se comporta igual que una condición falsa** — rinde vacío y cae al `default` sin
decir nada. No hay que reproducir eso.

### Por qué la decisión 3

Un programa que no compila es un error de configuración, no de runtime. Detectarlo
al cargar el YAML lo convierte en un fallo de despliegue con línea y mensaje, en
vez de un error en la cara del primer cliente que consulte.

Es también lo que hace que `max_repairs` deje de tener sentido en este modo: no hay
nada que reparar, porque un programa roto impide que el agente arranque.

## Arquitectura

Tres cambios. Dos son de cableado en el core y no existían — verificados sobre el
árbol al escribir este spec.

### 1 · El `context` del llamador tiene que llegar al patrón

Hoy **no llega**. `agent.run()` pasa `context=memory_context` al patrón
(`engine.py:1006`); el `context` que recibió el llamador se usa para renderizar el
prompt (`engine.py:875`) y para `_provider_override` (`engine.py:895`), y ahí
termina.

Se propaga metiéndolo en el dict que ya viaja, bajo una clave reservada — la misma
convención que ya usa `_history_messages`:

```python
context=({**memory_context, "_caller_context": context or {}}
         if isinstance(memory_context, dict) else memory_context)
```

`GlyphPattern` lo lee de ahí y lo expone al programa como la variable `context`.
Los demás patrones lo ignoran, como ignoran hoy `_history_messages`.

### 2 · `_build_pattern` necesita el catálogo para validar

`_build_pattern(spec)` sólo recibe el spec (definido en `engine.py:625`, invocado en
`engine.py:603`), pero el `ToolRegistry` del agente ya está construido para ese
momento (`engine.py:482`). Pasa a recibir también los schemas:

```python
pattern = self._build_pattern(spec, tools.get_tool_schemas(
    spec.get("permissions", {}).get("allowed_actions")))
```

Con eso, cuando el spec trae `program`, `_build_pattern` lo compila contra el
catálogo y deja que la excepción suba: el agente no carga.

### 3 · `GlyphPattern` salta la generación

```python
def __init__(self, max_repairs=2, narrate=True, program=None):
```

Cuando `program` está seteado, `execute()` no llama al modelo para escribirlo:
compila el programa fijo, lo ejecuta con `PatternCapabilities`, y sigue por el mismo
camino de siempre. `narrate` decide si redacta o devuelve JSON. Todo lo demás
—executor, compilador, adapter, `ask`— queda igual.

**`max_repairs` se ignora en este modo**, y no es un olvido: con programa fijo no
hay nada que reparar, porque uno que no compila impide que el agente cargue. Se deja
el parámetro por compatibilidad con los agentes que generan.

**La forma del resultado no cambia.** Un fallo de ejecución devuelve el mismo dict
que hoy —`{"answer", "steps", "glyph": {..., "failed": True}}`— para no romper a los
consumidores de la API. Lo que cambia es que no hay reintento ni fallback: se
ejecuta una vez, y si falla, falla.

### Las variables del programa

Dos, predefinidas en el entorno antes de ejecutar:

| variable | qué es |
|---|---|
| `query` | el texto crudo de la consulta |
| `context` | el dict del llamador, con acceso por punto: `context.order_id` |

Para sacar campos de texto libre está `ask()`, que ya existe:

```glyph
id = ask("Devolvé sólo el número de orden, sin nada más.", context=query)
orden = find_order(order_id=id)
```

Una extracción así son ~30 tokens de salida contra los ~8.000 de escribir el
programa: conserva el 99% del ahorro y cubre el caso de texto libre.

**El riesgo de `ask` es que devuelve texto, no estructura**, así que el modelo puede
agregar prosa alrededor del dato. Se mitiga con un prompt de extracción estricto, y
si resulta insuficiente en la práctica, el arreglo es un `ask_field()` con
validación — fuera del alcance de este spec.

## El ciclo de autoría

El modelo escribe, una persona revisa, el runtime ejecuta.

1. Se corre el agente **una vez** en modo generación (`pattern: glyph` sin
   `program`), con una consulta representativa.
2. El resultado trae ahora `glyph.program`: el texto del programa que el modelo
   escribió. Hoy queda en una variable local y se descarta.
3. Se lee, se corrige lo que haga falta —típicamente parametrizar lo que quedó
   hardcodeado de la consulta de autoría— y se pega en `spec.program`.
4. A partir de ahí el agente corre sin modelo.

Exponer `glyph.program` es todo lo que hace falta para cerrar el ciclo. Un comando
que automatice los pasos 1-3 es azúcar y queda fuera del alcance.

## Flujo de ejecución

```
bootstrap:  YAML → compile_program(program, catálogo) → agente cargado
            (si no compila, el agente no carga y el error dice la línea)

corrida:    query + context
              → env = {query, context}
              → execute(PlanGraph, PatternCapabilities)   ← cero llamadas al modelo
              → narrate ? redactar : JSON
```

## Errores

| cuándo | qué pasa |
|---|---|
| El programa no compila | El agente no carga. Error de despliegue con línea y mensaje. |
| Una capacidad falla en ejecución | El agente devuelve error, con el estado parcial. **No** cae a generar ni a `react`. |
| El programa referencia una tool que el agente no tiene permitida | No compila: el catálogo ya está filtrado por permisos. |
| `spec.program` presente con `pattern` distinto de `glyph` | El agente no carga, con un mensaje que lo diga. Es un error de configuración, no algo a ignorar. |

## Testing

- **El programa fijo no llama al modelo.** Un `model_fn` que explota si lo invocan,
  y un agente con `program` + `narrate: false`: la corrida tiene que completarse.
  Es la afirmación central del diseño.
- **`query` y `context` llegan al programa** con los valores que recibió el agente.
- **Un programa que no compila impide cargar el agente**, y el error trae la línea.
- **El `context` del llamador atraviesa `agent.run`** hasta el patrón — hoy no lo
  hace, así que sin este test la regresión es invisible.
- **Un fallo de capacidad devuelve error**, no un resultado vacío ni un fallback.
- **`spec.program` con otro `pattern` no carga.**
- **Los demás patrones siguen ignorando la clave nueva del context.**

## Alcance

**Entra:** `spec.program`, la propagación del context, la validación en bootstrap,
`glyph.program` en el resultado, un agente de ejemplo en `config/agents/`, y la
documentación del ciclo de autoría en `docs/GLYPH_GUIDE.md`.

**Queda afuera:** el caché por forma de consulta, `ask_field()`, y cualquier comando
que automatice la captura del programa.

## Riesgos

**El supuesto sin verificar es que un programa fijo cubra las consultas reales de un
agente.** Los escenarios del benchmark tienen una forma sola; un agente de producción
puede recibir variantes que el programa no contemple. El diseño elige fallar
explícito justamente para que eso se vea en vez de degradarse en silencio, pero la
frecuencia con que pase sólo se sabe usándolo.

**Un agente con programa fijo deja de ser conversacional.** No es una limitación del
diseño sino su consecuencia: si cada consulta necesita un plan distinto, este modo no
aplica y hay que usar `react`.

**La ventaja de confiabilidad (3/5 contra 1/5) es n=5.** Es la señal más consistente
de todos los datos y apareció con modelos distintos, pero no está confirmada
estadísticamente. Este diseño no depende de ella —su justificación es el costo— pero
tampoco hay que citarla como si estuviera cerrada.
