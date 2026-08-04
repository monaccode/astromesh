# Glyph — cuándo conviene, cómo medirlo y con qué modelo

Glyph es un patrón de orquestación alternativo a ReAct. En vez de pedirle al modelo
una acción por vuelta, le pide **un programa** que el runtime ejecuta entero,
encadenando tools localmente y en paralelo.

```yaml
spec:
  orchestration:
    pattern: glyph
```

Esta guía responde tres preguntas: **¿le conviene a mi agente?**, **¿cómo lo
compruebo?** y **¿con qué modelo?**

> Los números de este documento salen de `bench/glyph/`. Salvo la tasa de validez,
> son de una sola corrida contra un modelo que no es determinista ni con
> `temperature=0`. Diferencias de menos de ~2x están dentro del ruido. Medí lo
> tuyo antes de decidir — la última sección explica cómo, y cuesta centavos.

---

## 1 · La regla corta

**El ahorro crece con el largo de la cadena.** Medido sobre
`kimi-k2.7-code-highspeed`:

| escenario | tools que necesita | Δ tokens vs ReAct | ¿conviene? |
|---|---:|---:|---|
| consulta simple | 2 | **+382%** | no |
| búsqueda y comparación | 4 | **+14%** | indistinto |
| encadenamiento real | 6 | **−19%** | **sí** |

El umbral está **entre 4 y 6 tools**. Por debajo, el bloque de gramática que Glyph
agrega al prompt cuesta más que las vueltas que ahorra.

Es una decisión **por agente**, no global. Un agente de FAQ va con `react`; uno que
encadena seis sistemas va con `glyph`.

### Por qué el umbral existe

Glyph paga un costo fijo y cobra un beneficio variable.

**Costo fijo:** el bloque de gramática más el catálogo de capacidades, ~470 tokens
de entrada en cada corrida. En una tarea de dos tools, eso solo ya duplica el
prompt.

**Beneficio variable:** cada vuelta que ReAct no da es un contexto que no se
reenvía. En la cadena larga eso fue **−66% de tokens de entrada** — el mecanismo
completo del diseño, visible sólo cuando hay suficientes vueltas que eliminar.

Un detalle que suele sorprender: ReAct no gasta una llamada por tool. Los modelos
modernos emiten varias tool calls en una sola respuesta y `ReActPattern` las
ejecuta todas. Medido sobre la cadena larga, ReAct hizo `[1, 2, 2, 1, 0]` tool
calls por respuesta — 6 tools en 5 llamadas, no en 7. **Glyph compite contra un
ReAct que ya paraleliza**, y por eso el ahorro es menor de lo que la intuición
sugiere.

---

## 2 · Cuándo conviene

**Sí, si tu agente:**

- **Encadena cinco o más tools** donde cada resultado alimenta al siguiente.
- **Tiene ramales independientes.** `oem` y `alt` que no dependen entre sí corren
  en paralelo dentro de un programa; ReAct sólo puede pedirlos en la misma
  respuesta si el modelo se da cuenta.
- **Aplica una tool a cada elemento de una lista** — `equipos | map({g:
  garantia(sku=sku)})` dispara N llamadas concurrentes desde una sola vuelta.
- **Alimenta a otro agente** en vez de a una persona. Ahí `narrate: false` corta la
  segunda llamada al modelo entera.

**No, si tu agente:**

- **Resuelve con una o dos tools.** El costo fijo lo domina; medimos +382%.
- **Necesita ver los datos para decidir qué hacer después.** Glyph escribe el
  programa a ciegas. Hay un escape (`ask`, que consulta al modelo desde adentro
  del programa) pero cada uso es una vuelta que el programa eligió pagar, y si la
  decisión es siempre semántica no queda nada que ahorrar.
- **Corre sobre un modelo con razonamiento explícito.** Ver sección 4.
- **Es conversacional.** El costo fijo se paga en cada turno del chat.

---

## 3 · Cómo se configura

```yaml
spec:
  orchestration:
    pattern: glyph
    narrate: true      # default. false devuelve el resultado como JSON
    max_repairs: 2     # default. reintentos cuando el programa no compila
```

**`narrate: false`** salta la segunda llamada al modelo y devuelve el resultado del
programa como JSON. Es lo correcto para un agente que alimenta a otro eslabón: si
nadie va a leer la prosa, redactarla es una llamada de puro desperdicio. Con él
medimos **1 llamada al modelo contra las 4 de ReAct** en un escenario.

**`max_repairs`** acota los reintentos cuando el modelo escribe un programa que no
compila. Cada reparación cuesta una llamada entera al modelo, así que subirlo no
sale gratis; si necesitás más de 2, el problema es el modelo o la gramática.

Requiere el extra: `pip install 'astromesh[glyph]'`. Sin él, un agente que pida
`pattern: glyph` cae a `react` con un warning en vez de fallar el arranque.

---

## 4 · Qué modelo usar

**El modelo importa más que el agente.** Un mismo escenario cambia de −19% a +1000%
según con qué lo corras.

| perfil | validez | costo | veredicto |
|---|---|---|---|
| **Bueno en código, sin razonamiento** | 83-88% | −19% en cadena larga | **el que hay que usar** |
| **Con razonamiento explícito** | alta | **+621% a +1000%** | evitar |
| **Viejo o chico** | 38% | irrelevante, no compila | evitar |

### Por qué los modelos de razonamiento son tan caros acá

Escribir un programa en un lenguaje que nunca vieron dispara un chain-of-thought
enorme, y ese razonamiento se cobra como tokens de salida. `kimi-k2.5` gastó
**30.608 tokens de salida** para producir ocho líneas de programa, contra 1.086 que
gastó ReAct para la misma tarea. Emitir una tool call es un patrón que el modelo
vio millones de veces; escribir código en una gramática nueva es una tarea de
planificación.

Si tu proveedor deja desactivar el razonamiento, hacelo antes de descartar el
modelo.

### Por qué los modelos chicos fallan

No es que gasten de más: **no escriben Glyph válido**. Con `moonshot-v1-32k` la
tasa fue 38%, y un escenario falló 6 de 6 veces con el mismo error — trataba una
capacidad como si fuera una tabla (`search_parts | where(make == "Toyota")`) pese a
que la gramática lo prohíbe explícitamente. Cada fallo cuesta una reparación, y dos
reparaciones se comen cualquier ahorro.

### Qué mirar al elegir

La propiedad que predice el ajuste es **"escribe código bien y sin deliberar de
más"**. No hay que adivinarla: se mide en dos minutos con la herramienta de la
sección 5.

Los modelos verificados en este repo son de Moonshot, porque es la credencial que
había a mano. Para cualquier otro proveedor compatible con OpenAI el procedimiento
es idéntico — cambiás `BENCH_ENDPOINT` y medís.

---

## 5 · Cómo medir el tuyo

Dos herramientas, de barata a cara. **Empezá siempre por la primera.**

### 5.1 · Tasa de validez — dos minutos, centavos

Es la métrica que decide. Sólo hace la llamada de escritura del programa: sin
ejecutar tools, sin narración.

```bash
BENCH_MODEL=kimi-k2.7-code-highspeed \
BENCH_ENDPOINT=https://api.moonshot.ai/v1 \
BENCH_API_KEY_ENV=MOONSHOT_API_KEY \
N=6 uv run python -m bench.glyph.validity
```

```
## autolink-parts/cotizar-pastillas — 2/4
- **1x** GlyphSyntaxError: línea 4, columna 5: expresión inesperada: ''
- **1x** GlyphSyntaxError: línea 3, columna 66: expresión inesperada: '.'

**Global: 10/12 = 83%**
Apto: las reparaciones son raras y no se comen el ahorro.
```

Cómo leerlo:

| tasa | qué significa |
|---|---|
| **≥80%** | apto — las reparaciones son raras |
| **50-80%** | al límite — mirá si un error domina; suele arreglarse en la gramática |
| **<50%** | no apto — la reparación cuesta más que cualquier ahorro |

**Los errores se agrupan a propósito.** Un mismo fallo repetido seis veces es una
señal completamente distinta de seis fallos diferentes: el primero se arregla, el
segundo dice que el modelo no da.

### 5.2 · Benchmark completo — minutos, dólares

Corre cada escenario con `react`, `glyph` y `glyph-datos` (sin narración) contra el
mismo modelo y las mismas tools mockeadas, y reporta tokens, llamadas, latencia,
correctitud y programas inválidos.

```bash
BENCH_MODEL=... BENCH_ENDPOINT=... BENCH_API_KEY_ENV=... \
uv run python -m bench.glyph.run
```

| variable | default | para qué |
|---|---|---|
| `BENCH_MODEL` | — (requerida) | el modelo a medir |
| `BENCH_ENDPOINT` | `https://api.openai.com/v1` | cualquier endpoint compatible con OpenAI |
| `BENCH_API_KEY_ENV` | `OPENAI_API_KEY` | nombre de la variable con la credencial |
| `BENCH_TEMPERATURE` | sin fijar | fijala en 0 si el modelo la acepta |
| `BENCH_TIMEOUT` | 600 | segundos por llamada |

Las tools son mockeadas y deterministas a propósito: el benchmark mide **el
patrón**, y una tool que sale a la red mete variabilidad que ahoga la señal. Cada
una duerme un tiempo fijo para que la ganancia de concurrencia se vea en la
latencia.

Corre nightly en CI (`.github/workflows/bench-glyph.yml`), no en el gate de PR:
gasta dinero real. Las salidas quedan versionadas en `bench/glyph/results-*.md`.

### 5.3 · Medir tu propio agente

Los escenarios viven en `bench/glyph/fixtures.py`. Uno se agrega con un `Scenario`:

```python
MI_CASO = Scenario(
    name="mi-agente/caso-tipico",
    query="la consulta real que recibe el agente",
    tools=[
        _schema(
            "buscar_cliente",
            "Busca un cliente por email",
            {"email": {"type": "string"}},
            ["email"],
            "{customer_id, zip, tier}",   # <- la forma de lo que devuelve
        ),
    ],
    tool_impl={"buscar_cliente": _mi_mock},
    expected=lambda answer: "C-9" in answer,
    reference_program='cliente = buscar_cliente(email="a@b.com")\nreturn cliente',
)

SCENARIOS = [..., MI_CASO]
```

**El campo `returns` no es opcional en la práctica.** Sin él, el modelo tiene que
inventar los nombres de campo de lo que devuelve una tool — y en un lenguaje donde
el pipe filtra por campo, un campo inventado no da error: **filtra a vacío en
silencio**, que es peor. Hay un test que exige que todos los escenarios lo
declaren.

---

## 6 · Cómo optimizar

Lo que se probó, con resultados. La entrada es el ~27% del costo y la salida el
~73%, de la cual el 80-95% es razonamiento del modelo.

### Lo que funcionó

| optimización | ahorro | dónde |
|---|---|---|
| No reenviar la gramática en la narración | −466 t/corrida | ya aplicado |
| `narrate: false` | una llamada entera | por agente, en el YAML |
| Bloque de gramática como prefijo estable | habilita el caché del proveedor | ya aplicado |
| Eliminar reparaciones | una llamada con razonamiento c/u | arreglando la gramática |

**La palanca más rentable es eliminar reparaciones**, no recortar tokens. Cada
programa inválido cuesta una llamada completa de escritura, con todo su
razonamiento. Bajar la tasa de fallo del 40% al 10% vale más que cualquier recorte
del prompt.

### Lo que no funcionó

**Los ajustes de prompt.** Un A/B de cuatro variantes (ejemplo resuelto, "no
expliques", ambas) sobre tres escenarios: la varianza dentro de un mismo escenario
entre variantes fue **5,3x**, y el rango de los totales **1,27x**. El ruido domina;
no hay señal utilizable con n=1.

Dos cosas sí quedaron firmes en las 12 celdas: la prosa que el modelo escribe
alrededor del programa son **3 tokens** (así que suprimirla no ahorra nada), y
pedir "sólo código" **rompió la compilación dos veces** — parece suprimir también
la planificación que el modelo necesita.

**Achicar la gramática** tampoco mueve la aguja: son 372 tokens contra los miles de
salida. Hay un test que la mantiene acotada, pero recortarla más no es donde está
el dinero.

### Dónde mirar cuando algo va mal

| síntoma | causa probable | dónde se arregla |
|---|---|---|
| Tasa de validez baja, un error domina | la gramática no cubre algo que el modelo escribe | `prompt/grammar.py`, o el parser |
| Tasa baja, errores dispersos | el modelo no da | cambiar de modelo |
| Tokens de salida enormes | modelo con razonamiento | desactivarlo, o cambiar de modelo |
| Ahorro nulo con correctitud igual | la cadena es corta | usar `react` en ese agente |
| Latencia sin mejora | el programa no tiene sentencias independientes | revisar el escenario, no el motor |

### La lección que dejó construir esto

El benchmark encontró **ocho bugs** que 132 tests unitarios no encontraron, y todos
eran de la misma clase: **el modelo escribe Glyph como escribiría Python o JSON, y
el parser lo rechazaba.** Dicts multilínea, claves entre comillas, `None`, escapes
en strings, `{cliente.nombre}`, el mismo nombre en `if` y `else`.

Los tests fallaban en encontrarlos porque los escribió quien diseñó la gramática, y
escribían Glyph como el diseño lo imaginaba. **Toda capacidad nueva se valida
contra un modelo real antes de darla por hecha.**

---

## Ver también

- [`docs/GLYPH_ROADMAP.md`](GLYPH_ROADMAP.md) — las cuatro fases y qué depende de qué
- [`docs/superpowers/specs/2026-08-03-glyph-action-language-design.md`](superpowers/specs/2026-08-03-glyph-action-language-design.md) — el diseño, las decisiones y todas las corridas con su contexto
- [`astromesh-glyph/README.md`](../astromesh-glyph/README.md) — el lenguaje y su API
- `bench/glyph/results-*.md` — las salidas crudas de cada corrida
