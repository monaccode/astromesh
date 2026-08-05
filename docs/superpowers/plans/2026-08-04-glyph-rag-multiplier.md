# Multiplicador de RAG — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Medir cuánto multiplica un knowledge block de RAG contra las vueltas de cada patrón, para decidir si la fase 2 hay que construirla o ya está construida.

**Architecture:** El benchmark hoy llama al patrón con un `model_fn` pelado; producción antepone `rendered_prompt` como system en **cada** llamada (`astromesh/runtime/engine.py:906`). Se agrega un campo `knowledge` al `Scenario`, un envoltorio en `run_scenario` que reproduce ese comportamiento, y un escenario `support-agent-rag` que clona `support-agent` vía `dataclasses.replace()` y sólo le agrega el knowledge. Comparar las dos filas del reporte aísla la variable de forma exacta.

**Tech Stack:** Python 3.12+, `uv`, `pytest` (`asyncio_mode = "auto"`), `ruff` (line-length 100, target py312). Sin dependencias nuevas.

## Global Constraints

Aplican a **todas** las tareas.

- **Sin dependencias nuevas.** En particular, nada de tokenizers: los tokens de knowledge se **estiman** por `len(texto)//4` y se rotulan como estimación. El dato duro sigue siendo el `usage` que devuelve el proveedor.
- **Los escenarios existentes no cambian de comportamiento.** `knowledge` es `""` por defecto y las cuatro corridas ya versionadas en `bench/glyph/results-*.md` tienen que seguir siendo comparables.
- **`support-agent` y `support-agent-rag` comparten query, tools, `tool_impl`, `expected` y `reference_program`.** Sólo difieren en `name` y `knowledge`. Si divergen, la comparación deja de aislar la variable.
- **Este plan sólo mide.** Nada de pack de capacidades RAG, nada de pushdown, ningún cambio a `astromesh/rag/`.
- **Commits convencionales**: `feat:`, `fix:`, `chore:`, `test:`, `docs:`.
- **Regla de changelog**: sólo aplica a `feat:`/`fix:`/`refactor:` que toquen `astromesh/`. Este plan toca `bench/` y `docs/`, así que no exige entrada en `CHANGELOG.md`.
- Lint y formato antes de cada commit: `uv run ruff check bench/ tests/ && uv run ruff format bench/ tests/`.

---

## Estructura de archivos

| Archivo | Cambio |
|---|---|
| `bench/glyph/fixtures.py` | **Modificar** — campo `knowledge` en `Scenario`, chunks de políticas, `SUPPORT_RAG` |
| `bench/glyph/harness.py` | **Modificar** — `RunMetrics.knowledge_tokens_resent`, envoltorio de system en `run_scenario` |
| `bench/glyph/run.py` | **Modificar** — fila del reporte |
| `tests/test_bench_glyph.py` | **Modificar** — tests de las tres |
| `docs/superpowers/specs/2026-08-04-glyph-rag-multiplier-design.md` | **Modificar** — los resultados de la corrida |

---

## Task 1: El escenario con knowledge

**Files:**
- Modify: `bench/glyph/fixtures.py`
- Test: `tests/test_bench_glyph.py`

**Interfaces:**
- Consumes: `Scenario`, `SUPPORT` (ya existen en `bench/glyph/fixtures.py`).
- Produces: `Scenario.knowledge: str = ""`; la constante `KNOWLEDGE_POLITICAS: str`; el escenario `SUPPORT_RAG` con `name="support-agent-rag/devolucion"`; `SCENARIOS` pasa a tener cuatro entradas.

**Por qué `dataclasses.replace`:** garantiza por construcción que los dos escenarios comparten todo salvo lo que se pisa explícitamente. Copiar el escenario a mano dejaría la igualdad a merced de que nadie edite uno solo de los dos.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_bench_glyph.py`:

```python
def test_the_rag_scenario_shares_everything_but_knowledge_with_its_twin():
    """Es el test que sostiene el experimento.

    Si los dos escenarios divergen en algo más que el knowledge, el delta del
    reporte deja de ser puro multiplicador y los números siguen pareciendo
    válidos. El fallo sería silencioso.
    """
    from bench.glyph.fixtures import SUPPORT, SUPPORT_RAG

    assert SUPPORT_RAG.query == SUPPORT.query
    assert SUPPORT_RAG.tools == SUPPORT.tools
    assert SUPPORT_RAG.tool_impl == SUPPORT.tool_impl
    assert SUPPORT_RAG.expected is SUPPORT.expected
    assert SUPPORT_RAG.reference_program == SUPPORT.reference_program
    assert SUPPORT_RAG.name != SUPPORT.name


def test_only_the_rag_scenario_declares_knowledge():
    """Los escenarios viejos no cambian: las corridas versionadas siguen comparables."""
    from bench.glyph.fixtures import SUPPORT_RAG

    with_knowledge = [s.name for s in SCENARIOS if s.knowledge]
    assert with_knowledge == [SUPPORT_RAG.name]


def test_the_knowledge_block_is_the_size_of_a_real_retrieval():
    """5 chunks, que es el top_k de config/rag/product-knowledge.rag.yaml."""
    from bench.glyph.fixtures import KNOWLEDGE_POLITICAS

    assert KNOWLEDGE_POLITICAS.count("\n\n") == 4  # 5 chunks separados por línea en blanco
    assert 3000 < len(KNOWLEDGE_POLITICAS) < 6000  # ~750-1500 tokens


def test_the_knowledge_uses_the_production_renderer():
    """Si el formato de producción cambia, el benchmark cambia con él."""
    from astromesh.rag.agent_rag import format_knowledge

    from bench.glyph.fixtures import KNOWLEDGE_POLITICAS, POLITICAS_CHUNKS

    assert KNOWLEDGE_POLITICAS == format_knowledge(POLITICAS_CHUNKS)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_bench_glyph.py -q -k "rag_scenario or knowledge"
```

Esperado: FAIL — `ImportError: cannot import name 'SUPPORT_RAG'`.

- [ ] **Step 3: Agregar el campo al `Scenario`**

En `bench/glyph/fixtures.py`, dentro del `@dataclass class Scenario`, después de `reference_program`:

```python
    # Lo que AgentRAG.build_context() inyectaría en el prompt. Vacío en los
    # escenarios que no simulan RAG, para que sigan comparables con las corridas
    # ya versionadas en results-*.md.
    knowledge: str = ""
```

- [ ] **Step 4: Agregar los chunks y el escenario**

Al final de `bench/glyph/fixtures.py`, antes de la línea `SCENARIOS = [...]`:

```python
# ---- el mismo escenario, con knowledge ---------------------------------------
#
# `rendered_prompt` lleva los chunks y se antepone como system en CADA llamada al
# modelo (astromesh/runtime/engine.py:906). Un agente RAG con ReAct y seis vueltas
# paga sus chunks seis veces. Este escenario mide cuánto pesa eso.
#
# Clona a SUPPORT a propósito: es donde Glyph pierde peor (+382% en tokens con
# kimi-k2.7-code-highspeed), porque con dos tools el costo fijo de la gramática
# domina. Si el knowledge da vuelta ESE caso, el multiplicador es fuerte de verdad.

POLITICAS_CHUNKS = [
    {
        "content": (
            "Política de devoluciones — plazo general. El cliente dispone de 30 días "
            "corridos desde la fecha de entrega para solicitar la devolución de un "
            "producto. El plazo se cuenta desde que la orden figura como entregada en "
            "el sistema, no desde la fecha de compra. Pasados los 30 días la solicitud "
            "se rechaza automáticamente salvo que aplique alguna de las excepciones "
            "detalladas más abajo. El plazo es el mismo para compras en tienda física "
            "y en el canal online."
        )
    },
    {
        "content": (
            "Política de devoluciones — requisitos. Toda devolución exige el "
            "comprobante de compra, que puede ser el ticket físico o el número de "
            "orden. El producto debe estar en su empaque original, con todos sus "
            "accesorios y sin señales de uso más allá de lo necesario para probarlo. "
            "Los productos de higiene personal y la ropa interior no se aceptan una "
            "vez abiertos, por normativa sanitaria."
        )
    },
    {
        "content": (
            "Política de devoluciones — excepciones al plazo. Un producto con falla de "
            "fábrica se puede devolver durante todo el período de garantía, que es de "
            "12 meses. Los productos comprados durante las liquidaciones de fin de "
            "temporada tienen un plazo reducido de 15 días. Las compras hechas como "
            "regalo pueden extender el plazo hasta 60 días si se declara al momento "
            "de la compra."
        )
    },
    {
        "content": (
            "Reembolsos — plazos y medios. El reembolso se acredita en el mismo medio "
            "de pago usado en la compra. En tarjeta de crédito puede demorar hasta dos "
            "ciclos de facturación, según el emisor. En transferencia y débito el plazo "
            "es de 5 a 10 días hábiles desde que se aprueba la devolución. No se emiten "
            "reembolsos en efectivo por compras online."
        )
    },
    {
        "content": (
            "Proceso de devolución — pasos. El agente verifica la orden y la fecha de "
            "entrega, confirma que se cumplan los requisitos, y abre un ticket de "
            "devolución. El ticket genera una etiqueta de envío prepaga que se manda al "
            "correo del cliente. Una vez recibido el producto en depósito, control de "
            "calidad tiene 3 días hábiles para aprobarlo y disparar el reembolso."
        )
    },
]

KNOWLEDGE_POLITICAS = format_knowledge(POLITICAS_CHUNKS)

SUPPORT_RAG = replace(
    SUPPORT,
    name="support-agent-rag/devolucion",
    knowledge=KNOWLEDGE_POLITICAS,
)
```

Y actualizar la última línea del archivo:

```python
SCENARIOS = [AUTOLINK, SUPPORT, SUPPORT_RAG, LONG_CHAIN]
```

- [ ] **Step 5: Agregar los imports**

Al principio de `bench/glyph/fixtures.py`, junto a los demás:

```python
from dataclasses import dataclass, replace

from astromesh.rag.agent_rag import format_knowledge
```

El import de `format_knowledge` es deliberado y no una comodidad: si el formato de
producción cambia, el benchmark cambia con él en vez de medir un formato que ya no
existe.

- [ ] **Step 6: Correr los tests**

```bash
uv run pytest tests/test_bench_glyph.py -q
```

Esperado: PASS. Si `test_the_knowledge_block_is_the_size_of_a_real_retrieval` falla
por longitud, ajustar el texto de los chunks — no el rango del test, que refleja lo
que devuelve un `top_k: 5` real.

- [ ] **Step 7: Lint, formato y commit**

```bash
uv run ruff check bench/ tests/ && uv run ruff format bench/ tests/
git add bench/glyph/fixtures.py tests/test_bench_glyph.py
git commit -m "test(glyph): escenario support-agent-rag con knowledge block"
```

---

## Task 2: El system prompt en cada llamada

**Files:**
- Modify: `bench/glyph/harness.py`
- Test: `tests/test_bench_glyph.py`

**Interfaces:**
- Consumes: `Scenario.knowledge` (Task 1), `CountingModel`, `RunMetrics`.
- Produces: `RunMetrics.knowledge_tokens_resent: int` (último campo, default `0`); `run_scenario` antepone el system cuando el escenario declara knowledge.

**El detalle que decide la medición:** el envoltorio va **entre el patrón y
`CountingModel`**, nunca adentro. Así el proveedor recibe el system y su `usage` lo
cobra, que es exactamente lo que pasa en producción. Si el envoltorio fuera después
de `CountingModel`, los tokens del knowledge no aparecerían en el conteo y la
medición daría cero.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_bench_glyph.py`:

```python
async def test_the_knowledge_is_prepended_as_system_on_every_model_call():
    """Es el punto entero de la medición: producción lo reenvía en cada llamada.

    Va con GlyphPattern y un programa válido a propósito: hace dos llamadas
    (escribir y narrar), así el test comprueba «en cada llamada» y no sólo «en la
    primera». Con un ReAct que responde de una, el aserto sería vacío.
    """
    from bench.glyph.fixtures import SUPPORT_RAG

    seen = []
    program = "```glyph\n" + SUPPORT_RAG.reference_program + "\n```"
    responses = iter([program, "listo"])

    async def provider_fn(messages, tools, role=None):
        seen.append(messages)

        class R:
            content = next(responses)
            tool_calls = None
            usage = {"input_tokens": 10, "output_tokens": 5}

        return R()

    await run_scenario(SUPPORT_RAG, GlyphPattern(), CountingModel(provider_fn))

    assert len(seen) == 2
    for messages in seen:
        assert messages[0]["role"] == "system"
        assert "30 días corridos" in messages[0]["content"]


async def test_a_scenario_without_knowledge_gets_no_system_message():
    """Los escenarios viejos no cambian: las corridas versionadas siguen comparables."""
    from bench.glyph.fixtures import SUPPORT

    seen = []

    async def provider_fn(messages, tools, role=None):
        seen.append(messages)

        class R:
            content = "listo"
            tool_calls = None
            usage = {"input_tokens": 10, "output_tokens": 5}

        return R()

    await run_scenario(SUPPORT, ReActPattern(), CountingModel(provider_fn))
    assert all(m[0]["role"] != "system" for m in seen)


async def test_knowledge_tokens_resent_multiplies_by_model_calls():
    from bench.glyph.fixtures import KNOWLEDGE_POLITICAS, SUPPORT_RAG

    model = CountingModel(_scripted(["listo"] * 20))
    metrics = await run_scenario(SUPPORT_RAG, ReActPattern(), model)

    assert metrics.knowledge_tokens_resent == len(KNOWLEDGE_POLITICAS) // 4 * model.calls
    assert metrics.knowledge_tokens_resent > 0


async def test_a_scenario_without_knowledge_resends_nothing():
    from bench.glyph.fixtures import SUPPORT

    metrics = await run_scenario(SUPPORT, ReActPattern(), CountingModel(_scripted(["ok"] * 20)))
    assert metrics.knowledge_tokens_resent == 0


async def test_a_provider_failure_travels_through_the_wrapper():
    """Un envoltorio que se traga la excepción convertiría un fallo en un resultado."""
    from bench.glyph.fixtures import SUPPORT_RAG

    async def provider_fn(messages, tools, role=None):
        raise RuntimeError("503 del proveedor")

    with pytest.raises(RuntimeError, match="503"):
        await run_scenario(SUPPORT_RAG, ReActPattern(), CountingModel(provider_fn))
```

Y agregar los imports que faltan al principio de `tests/test_bench_glyph.py`:

```python
import pytest

from astromesh.orchestration.patterns import ReActPattern
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_bench_glyph.py -q -k "prepended or resent or travels or without_knowledge"
```

Esperado: FAIL — `AssertionError` en el system (aún no se antepone) y
`AttributeError: 'RunMetrics' object has no attribute 'knowledge_tokens_resent'`.

- [ ] **Step 3: Agregar el campo a `RunMetrics`**

En `bench/glyph/harness.py`, como último campo del dataclass:

```python
@dataclass
class RunMetrics:
    scenario: str
    pattern: str
    input_tokens: int
    output_tokens: int
    model_calls: int
    tool_calls: int
    wall_ms: float
    correct: bool
    invalid_programs: int
    # Estimación por caracteres/4: no hay tokenizer en el repo y agregarlo por una
    # fila de reporte no se justifica. El dato duro es `input_tokens`, que sale del
    # `usage` del proveedor; esto existe para hacer visible el mecanismo.
    knowledge_tokens_resent: int = 0
```

Va con default porque `render_report` se testea con `RunMetrics` construidos a mano
en `tests/test_bench_glyph.py`, y esos no deberían tener que declararlo.

- [ ] **Step 4: Anteponer el system y calcular la métrica**

En `bench/glyph/harness.py`, dentro de `run_scenario`, después de definir `tool_fn`
y antes de `started = time.monotonic()`:

```python
    # Producción antepone `rendered_prompt` —que lleva los chunks de RAG— como
    # system en cada llamada (astromesh/runtime/engine.py:906). Reproducirlo es lo
    # que hace medible el multiplicador.
    #
    # El envoltorio va ENTRE el patrón y CountingModel, no adentro: así el
    # proveedor recibe el system y su `usage` lo cobra. Al revés, los tokens del
    # knowledge no aparecerían en el conteo y la medición daría cero.
    model_fn: Any = model
    if scenario.knowledge:
        system = {"role": "system", "content": scenario.knowledge}

        async def with_knowledge(messages, tools, role=None):
            return await model([system, *messages], tools, role=role)

        model_fn = with_knowledge
```

Cambiar `model_fn=model` por `model_fn=model_fn` en la llamada a `pattern.execute()`.

Y en el `RunMetrics` que devuelve, agregar como último argumento:

```python
        knowledge_tokens_resent=len(scenario.knowledge) // 4 * model.calls,
```

- [ ] **Step 5: Correr los tests**

```bash
uv run pytest tests/test_bench_glyph.py -q
```

Esperado: PASS.

- [ ] **Step 6: Lint, formato y commit**

```bash
uv run ruff check bench/ tests/ && uv run ruff format bench/ tests/
git add bench/glyph/harness.py tests/test_bench_glyph.py
git commit -m "test(glyph): reproducir el system prompt de producción en el benchmark"
```

---

## Task 3: La fila del reporte

**Files:**
- Modify: `bench/glyph/run.py`
- Test: `tests/test_bench_glyph.py`

**Interfaces:**
- Consumes: `RunMetrics.knowledge_tokens_resent` (Task 2), `_row(label, baseline, values)`.
- Produces: la fila `Knowledge reenviado (est.)` en `render_report()`, presente sólo cuando alguna variante la tiene distinta de cero.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_bench_glyph.py`:

```python
def test_the_report_shows_the_resent_knowledge_when_there_is_any():
    report = render_report(
        [
            _metrics("react", knowledge_tokens_resent=6000),
            _metrics("glyph", knowledge_tokens_resent=2000),
        ]
    )
    assert "| Knowledge reenviado (est.) | 6000 | 2000 (-67%) |" in report


def test_the_report_omits_the_row_when_no_scenario_has_knowledge():
    """Las corridas versionadas no tienen knowledge; su reporte no debería cambiar."""
    report = render_report([_metrics("react"), _metrics("glyph")])
    assert "Knowledge reenviado" not in report


def test_the_knowledge_row_sits_next_to_the_token_rows():
    """Va después de los totales, que es donde se lee como parte del gasto."""
    report = render_report(
        [
            _metrics("react", knowledge_tokens_resent=6000),
            _metrics("glyph", knowledge_tokens_resent=2000),
        ]
    )
    lines = report.splitlines()
    totales = next(i for i, x in enumerate(lines) if "Tokens totales" in x)
    knowledge = next(i for i, x in enumerate(lines) if "Knowledge reenviado" in x)
    llamadas = next(i for i, x in enumerate(lines) if "Llamadas al modelo" in x)
    assert totales < knowledge < llamadas
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

```bash
uv run pytest tests/test_bench_glyph.py -q -k "knowledge_row or resent_knowledge or omits"
```

Esperado: FAIL — `AssertionError`, la fila no existe.

- [ ] **Step 3: Agregar la fila**

En `bench/glyph/run.py`, dentro de `render_report`, reemplazar el bloque
`lines.extend([...])` de la tabla por:

```python
        rows = [
            f"| Métrica | ReAct | {header} |",
            "|---" * (2 + len(others)) + "|",
            _row("Tokens de entrada", react.input_tokens, [m.input_tokens for _, m in others]),
            _row("Tokens de salida", react.output_tokens, [m.output_tokens for _, m in others]),
            _row("Tokens totales", _total(react), [_total(m) for _, m in others]),
        ]
        # Sólo cuando el escenario simula RAG: en los demás la fila sería una
        # columna de ceros, y el reporte de las corridas ya versionadas cambiaría
        # sin motivo.
        if react.knowledge_tokens_resent or any(m.knowledge_tokens_resent for _, m in others):
            rows.append(
                _row(
                    "Knowledge reenviado (est.)",
                    react.knowledge_tokens_resent,
                    [m.knowledge_tokens_resent for _, m in others],
                )
            )
        rows.extend(
            [
                _row("Llamadas al modelo", react.model_calls, [m.model_calls for _, m in others]),
                _row("Llamadas a tools", react.tool_calls, [m.tool_calls for _, m in others]),
                _row("Latencia (ms)", round(react.wall_ms), [round(m.wall_ms) for _, m in others]),
                "| Respuesta correcta | "
                + " | ".join([_mark(react.correct)] + [_mark(m.correct) for _, m in others])
                + " |",
                "| Programas inválidos | — | "
                + " | ".join(str(m.invalid_programs) for _, m in others)
                + " |",
                "",
            ]
        )
        lines.extend(rows)
```

- [ ] **Step 4: Correr toda la suite**

```bash
uv run pytest tests/test_bench_glyph.py -q && uv run pytest -q
```

Esperado: PASS en las dos. La suite completa importa acá: `render_report` lo usan
otros tests que no deberían haberse roto.

- [ ] **Step 5: Lint, formato y commit**

```bash
uv run ruff check bench/ tests/ && uv run ruff format bench/ tests/
git add bench/glyph/run.py tests/test_bench_glyph.py
git commit -m "test(glyph): fila de knowledge reenviado en el reporte"
```

---

## Task 4: Correr y publicar el resultado

**Files:**
- Create: `bench/glyph/results-2026-08-04-rag-multiplier.md`
- Modify: `docs/superpowers/specs/2026-08-04-glyph-rag-multiplier-design.md`
- Modify: `docs/GLYPH_GUIDE.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: los números y la decisión sobre la fase 2.

**Modelo:** `kimi-k2.7-code-highspeed`, el único de los tres medidos en la fase 1
que resultó apto (88% de programas válidos al primer intento). Medir el
multiplicador con un modelo que no escribe Glyph válido mezclaría dos efectos.

- [ ] **Step 1: Correr el benchmark**

La corrida tarda varios minutos; lanzarla en segundo plano y esperar la
notificación en vez de bloquear:

```bash
MOONSHOT_API_KEY=$(KUBECONFIG=~/.kube/fainansu-yavin.yaml kubectl -n clarus-dev \
  get secret clarus-agents-secret -o jsonpath='{.data.MOONSHOT_API_KEY}' | base64 -d) \
BENCH_MODEL=kimi-k2.7-code-highspeed \
BENCH_ENDPOINT=https://api.moonshot.ai/v1 \
BENCH_API_KEY_ENV=MOONSHOT_API_KEY \
uv run python -u -m bench.glyph.run > bench/glyph/results-2026-08-04-rag-multiplier.md 2>&1
```

- [ ] **Step 2: Leer las dos filas que importan**

Comparar `support-agent/devolucion` contra `support-agent-rag/devolucion`. Son el
mismo escenario; el delta entre ellos es el multiplicador.

- [ ] **Step 3: Escribir el resultado en el spec**

Agregar una sección `## Resultado` al final de
`docs/superpowers/specs/2026-08-04-glyph-rag-multiplier-design.md` con las dos
tablas y el desenlace, según lo que ya declara la sección «Cómo se lee el
resultado» del spec:

| desenlace | qué se escribe |
|---|---|
| Da vuelta el +382% | el multiplicador es real; la fase 2 ya está construida y lo que falta es documentarla |
| Lo achica sin darlo vuelta | el umbral de la guía se corre; decir a cuánto |
| No lo mueve | la premisa de la fase 2 es falsa; se cierra y se pasa a la fase 3 |

Incluir la advertencia de siempre: es n=1 contra un modelo no determinista, y si el
efecto queda por debajo de 2x no es concluyente.

- [ ] **Step 4: Actualizar la guía si el resultado lo amerita**

Si el multiplicador resulta real, `docs/GLYPH_GUIDE.md` necesita dos cambios:

- En **§1 · La regla corta**, agregar que el umbral baja cuando el agente tiene
  knowledge block, con el número medido.
- En **§2 · Cuándo conviene**, agregar «tiene un knowledge block de RAG» a la lista
  del *sí*, explicando que el bloque se reenvía en cada vuelta.

Si el multiplicador no aparece, la guía no se toca y se anota el resultado negativo
en el spec. **Un resultado negativo también se publica.**

- [ ] **Step 5: Commit**

```bash
git add bench/glyph/results-2026-08-04-rag-multiplier.md \
        docs/superpowers/specs/2026-08-04-glyph-rag-multiplier-design.md docs/GLYPH_GUIDE.md
git commit -m "docs(glyph): resultado del multiplicador de RAG"
```

---

## Cierre

Con el número en la mano, la decisión sobre la fase 2 tiene tres caminos y los tres
están escritos de antemano en el spec. Ninguno requiere volver a discutir el
diseño: el experimento se armó para que el resultado decida solo.
