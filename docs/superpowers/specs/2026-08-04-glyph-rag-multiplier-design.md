# Medir el multiplicador de RAG (fase 2, paso 0)

**Fecha:** 2026-08-04
**Estado:** diseño aprobado, pendiente de plan de implementación
**Alcance:** `bench/glyph/` — un campo, un escenario, un envoltorio y una fila de reporte

## Por qué esto y no la fase 2 que decía el roadmap

El roadmap describe la fase 2 como «pack de capacidades RAG + pushdown de pipes al
store», y deja anotado un asterisco: *verificar primero si el pipeline de retrieval
ya es configuración fija y no decisión del modelo*.

Se verificó. El asterisco se confirma, y peor de lo previsto.

### Hallazgo 1 — el modelo no decide nada sobre retrieval, y no puede

```python
# astromesh/rag/pipeline.py
async def query(self, query: str, top_k: int = 5) -> RAGResult:
```

`top_k` es el único parámetro por consulta. Chunker, embedder, store y reranker se
fijan al construir el pipeline desde el YAML.

Y RAG **ni siquiera es una tool**: `AgentRAG.build_context()` corre *antes* del
patrón de orquestación y su salida entra al prompt renderizado
(`engine.py:869-876`). El modelo nunca la pide ni la puede modular.

O sea, «el modelo elige un pipeline distinto por consulta» no es un caso raro que
haya que cuantificar: hoy es imposible.

### Hallazgo 2 — el que sí importa

```python
# astromesh/runtime/engine.py:906
full_messages = [{"role": "system", "content": rendered_prompt}, *messages]
```

`rendered_prompt` contiene los chunks, y ese system se antepone **en cada llamada
al modelo**. Un agente RAG con ReAct y seis vueltas paga sus chunks seis veces.

Con `top_k: 5` (el valor de `config/rag/product-knowledge.rag.yaml`) y chunks de
~200 tokens, son ~1.000 tokens de knowledge. Seis vueltas son 6.000; dos vueltas
son 2.000.

**Ese ahorro sería mayor que todo lo medido en la fase 1, y no necesita una línea
de código nueva:** es automático hoy con `pattern: glyph`. La fase 1 lo habilitó
sin que nadie lo notara, porque ningún escenario del benchmark tiene knowledge
block.

### Hallazgo 3 — el pushdown vale menos de lo que decía el roadmap

En un programa Glyph los chunks **nunca entran al contexto del LLM**: viven en el
runtime. Empujar el filtro al store ahorra trabajo de red y de base de datos, no
tokens. Además `VectorStore.search()` sólo soporta filtros de igualdad sobre
metadata (`qdrant.py:57-63`, `pgvector.py:66-72`); no hay umbral de score en la
interfaz.

### La conclusión

La fase 2 como estaba escrita ataca lo que menos rinde. **Antes de diseñarla hay
que medir el multiplicador**, porque el número decide si hace falta construir algo
o si ya está construido.

## Qué se construye

Un escenario de benchmark que reproduce el system prompt de producción, para medir
cuánto multiplica el knowledge block contra las vueltas de cada patrón.

Nada de pack RAG. Nada de pushdown. Eso se decide después, con el número.

## Decisiones de diseño

| # | Decisión | Alternativa descartada |
|---|---|---|
| 1 | El knowledge se antepone como **system en cada llamada**, igual que `engine.py:906` | Meterlo una vez en el primer mensaje de usuario |
| 2 | Chunks **hardcodeados**, renderizados con el `format_knowledge()` real | Levantar un store y un pipeline de verdad |
| 3 | Escenario nuevo que **clona `support-agent`** y sólo agrega knowledge | Agregarle knowledge al escenario existente |
| 4 | Se elige el escenario donde Glyph **pierde peor** | El escenario donde ya gana |
| 5 | Los tokens de knowledge se **estiman** por caracteres/4, y se dice que es estimación | Agregar `tiktoken` como dependencia |

### Por qué la decisión 3

`support-agent-rag` comparte **query y tools** con `support-agent`; lo único que
cambia es el knowledge. Comparar las dos filas del reporte aísla la variable de
forma exacta: el delta es puro multiplicador, sin nada más moviéndose.

Agregarle knowledge al escenario existente habría roto la comparabilidad con las
cuatro corridas ya versionadas en `bench/glyph/results-*.md`.

### Por qué la decisión 4

`support-agent` es donde Glyph pierde peor de los tres: **+382%** en tokens contra
ReAct, porque con dos tools el costo fijo de la gramática domina.

Si el knowledge da vuelta *ese* caso, el multiplicador es fuerte de verdad. Si no
lo da vuelta ahí, la premisa de la fase 2 es débil y nos enteramos por el precio de
una corrida en vez del de una fase entera.

Elegir la cadena larga habría sido apilar el mazo: ahí Glyph ya gana sin knowledge.

### Por qué la decisión 5

No hay tokenizer en el repo y agregar uno por una fila de reporte no se justifica.
El número existe para hacer visible el mecanismo —*los chunks se reenvían N
veces*—, no para contabilidad fina. Va rotulado como estimación, y el dato duro
sigue siendo el conteo de `usage` que devuelve el proveedor.

## Arquitectura

Tres cambios, todos en `bench/glyph/`.

### 1 · `Scenario` suma `knowledge`

```python
@dataclass
class Scenario:
    ...
    knowledge: str = ""   # lo que AgentRAG.build_context() inyectaría
```

Vacío por defecto: los escenarios existentes no cambian de comportamiento.

### 2 · `run_scenario` antepone el system

```python
model_fn = model
if scenario.knowledge:
    async def model_fn(messages, tools, role=None):
        return await model(
            [{"role": "system", "content": scenario.knowledge}, *messages], tools, role=role
        )
```

El envoltorio va **entre el patrón y `CountingModel`**, no adentro: así el
proveedor ve el system y su `usage` lo cobra, que es exactamente lo que pasa en
producción. Un envoltorio que no propague una excepción escondería fallos del
proveedor como si fueran resultados; se limita a delegar.

### 3 · El escenario

`support-agent-rag`, con la query, las tools y el `expected` de `support-agent`, y
un knowledge de cinco chunks de una base de conocimiento de políticas —el
arquetipo de agente RAG— renderizados con la función de producción:

```python
from astromesh.rag.agent_rag import format_knowledge

_POLITICAS = [
    {"content": "Devoluciones. El plazo es de 30 días corridos desde ..."},
    ...   # 5 chunks, ~200 tokens cada uno
]
KNOWLEDGE = format_knowledge(_POLITICAS)
```

Usar `format_knowledge()` y no un `"\n\n".join()` propio es deliberado: si el
formato de producción cambia, el benchmark cambia con él.

### 4 · Una fila en el reporte

`RunMetrics` suma `knowledge_tokens_resent: int`, calculado en `run_scenario` como
`len(scenario.knowledge)//4 * model_calls` — cero cuando el escenario no declara
knowledge. El reporte lo muestra como una fila más, y sólo cuando alguna variante
la tiene distinta de cero:

```
| Knowledge reenviado (est.) | 6000 | 2000 (-67%) |
```

Hace explícito el mecanismo en vez de dejarlo inferir del total de entrada.

## Flujo

```
run_scenario(support-agent-rag, ReActPattern, model)
  → cada llamada del patrón pasa por el envoltorio
  → el envoltorio antepone el system con los 5 chunks
  → CountingModel acumula el usage que devuelve el proveedor
  → RunMetrics.knowledge_tokens_resent = est. del bloque × model_calls
```

## Cómo se lee el resultado

Dos filas del reporte, mismo escenario con y sin knowledge:

| | qué significaría |
|---|---|
| `support-agent-rag` **da vuelta** el +382% | el multiplicador es real y grande; **la fase 2 ya está construida** y lo que falta es documentarlo y medir cuánto |
| Lo achica pero no lo da vuelta | el multiplicador existe pero no alcanza en cadenas cortas; el umbral de la guía se corre y hay que decir cuánto |
| No lo mueve | la premisa de la fase 2 es falsa; se cierra y se pasa a la fase 3 |

**No hay umbral automático.** Los tres desenlaces son informativos y los tres se
publican.

## Testing

- **El system se antepone en cada llamada**, no sólo en la primera — es el punto
  entero de la medición.
- **Un escenario sin knowledge no agrega system**, para que las cuatro corridas ya
  versionadas sigan siendo comparables.
- **`support-agent` y `support-agent-rag` comparten query y tools.** Si alguien las
  hace divergir, la comparación deja de aislar la variable y el test tiene que
  gritar. Es el más importante de la lista: sin él, el experimento puede
  degradarse en silencio y seguir dando números que parecen válidos.
- **La fila del reporte** aparece sólo cuando hay knowledge, y multiplica por las
  llamadas al modelo.
- Las excepciones del proveedor **atraviesan el envoltorio** en vez de convertirse
  en un resultado vacío.

## Alcance

**Entra:** el campo, el envoltorio, el escenario, la fila del reporte, sus tests, y
una corrida contra `kimi-k2.7-code-highspeed` (el modelo apto medido en la fase 1)
con sus números en este spec.

**Queda afuera:** el pack de capacidades RAG, el pushdown al store, y cualquier
cambio a `astromesh/rag/`. Este spec sólo mide.

## Riesgos

**El escenario de dos tools es demasiado corto para que el multiplicador se note.**
Es justamente lo que se quiere averiguar, y por eso se eligió el caso más
desfavorable. Si el resultado es ambiguo, el paso siguiente es agregar knowledge
también a la cadena larga.

**Las mediciones siguen siendo n=1.** Vale la advertencia de la fase 1: el modelo no
es determinista ni con `temperature=0`, y diferencias menores a ~2x están dentro
del ruido. El multiplicador esperado es de 3x o más, así que debería sobresalir —
si el resultado queda por debajo de 2x, no es concluyente y hay que repetirlo.

## Resultado (2026-08-04, `kimi-k2.7-code-highspeed`)

Salida cruda en `bench/glyph/results-2026-08-04-rag-multiplier.md`.

**El desenlace es el segundo de los tres previstos: el multiplicador achica la
penalidad de forma grande, pero no da vuelta el total.** Y hay un matiz que importa
más que el titular.

### Los dos escenarios gemelos, misma corrida

| | `support-agent` (sin knowledge) | `support-agent-rag` (con knowledge) |
|---|---:|---:|
| **Tokens de entrada** — glyph | +103% | **+75%** |
| **Tokens de entrada** — glyph-datos | +46% | **−35%** |
| **Tokens totales** — glyph | +292% | **+117%** |
| **Tokens totales** — glyph-datos | +997% | **+46%** |

El diseño de escenario gemelo rindió exactamente para lo que se eligió: la
comparación vive dentro de una sola corrida, así que la varianza entre corridas
—que en la fase 1 llegó a 5x— no la contamina. Comparar contra el +382% de la
corrida del 2026-08-04 anterior habría sido comparar ruido.

### Lo que sí se dio vuelta

**Los tokens de entrada de `glyph-datos` cruzaron a negativo: −35%.** 2.229 contra
3.449 de ReAct. Es la primera vez en todo el proyecto que Glyph gana en entrada en
un escenario de cadena corta, que es justo donde venía perdiendo peor.

La fila nueva del reporte lo hace explícito:

| Knowledge reenviado (est.) | ReAct | glyph | glyph-datos |
|---|---:|---:|---:|
| | 2.678 | 4.017 (+50%) | **1.339 (−50%)** |

ReAct hizo 2 llamadas y pagó el bloque dos veces; `glyph-datos` hizo 1 y lo pagó
una. El mecanismo funciona tal como el hallazgo 2 lo predijo.

### Por qué el total sigue positivo

Porque el knowledge sólo toca la entrada, y en Glyph **la salida es el 60-70% del
costo**: escribir el programa sigue costando 2.098 tokens de salida contra 288 de
ReAct. El multiplicador no puede compensar un componente que no afecta.

O sea: **el knowledge no cambia la naturaleza del trade-off, corre el umbral.** Un
agente con RAG necesita una cadena más corta que uno sin RAG para que Glyph le
convenga, porque arranca con una ventaja de entrada que antes no tenía.

### Un dato que no hay que leer

`glyph-datos` en `support-agent` dio +997%, con **7.623 tokens de salida en una
sola llamada al modelo**. Es un valor atípico —el modelo se fue de tema escribiendo
el programa— y hace parecer que el knowledge mejora las cosas 20x. No: la
comparación honesta es la de `glyph` con narración, +292% → +117%, que es una
penalidad partida a la mitad. Ya es un resultado fuerte sin necesidad de inflarlo.

### Qué se decide

**La fase 2 no hay que construirla: ya está construida.** El beneficio de RAG sale
del mismo mecanismo de la fase 1 —menos vueltas, menos contexto reenviado— y llega
gratis con `pattern: glyph`. No hace falta un pack de capacidades RAG para
obtenerlo.

Queda pendiente de decidir, con este número a la vista, si vale la pena convertir
retrieval en una capacidad del programa (lo que permitiría traer 40 candidatos y
filtrar a 3 localmente, atacando **la entrada** una segunda vez) o si conviene
pasar directo a la fase 3. El pushdown al store sigue siendo lo que menos rinde de
las tres opciones.

### La advertencia, otra vez

Esto es **n=1**. Lo que se sostiene es el signo y el orden de magnitud del efecto en
la entrada, que es grande (−35% contra +46%) y monotónico en las cuatro
comparaciones. Los totales están contaminados por la varianza de la salida, que en
la fase 1 llegó a 5x entre corridas idénticas.
