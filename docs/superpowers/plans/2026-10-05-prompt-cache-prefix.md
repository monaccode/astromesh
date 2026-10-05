# Prefijo estable para el caché de prompts (`prompts.context`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que lo que cambia por query (RAG, prefetch) viaje en un template nuevo `prompts.context`, pegado al mensaje del usuario actual, para que system → tools → historial sean un prefijo estable que el caché automático de Kimi/Moonshot pueda servir.

**Architecture:** Los patrones `react` y `glyph` anteponen `context["_turn_context"]` a la query con un helper único (`with_turn_context`) y se marcan con `consumes_turn_context = True`. `Agent.run` renderiza `prompts.context`, suma sus tokens a la base del presupuesto y lo entrega por `_turn_context` (o al final del system si el patrón no lo consume). Warnings al cargar y `cache.hit_ratio` en el span `llm.complete`.

**Tech Stack:** Python 3.12, pytest (asyncio auto), Jinja2 sandbox (`PromptEngine`), astromesh_glyph (extra instalado en dev).

**Spec:** `docs/superpowers/specs/2026-10-05-prompt-cache-prefix-design.md`

## Global Constraints

- `astromesh/api/main.py` tiene que importar sin extras: nada nuevo a nivel de módulo que dependa de `astromesh_glyph` o litellm.
- Orden resultante del prompt: system → tools → historial → [gramática glyph] → **contexto + query**.
- Formato de la query con contexto: string → `f"{turn_context}\n\n{query}"`; lista (multimodal) → `[{"type": "text", "text": turn_context}, *query]`; contexto `None`/vacío → query intacta.
- El turno de usuario persistido es la query original, sin el contexto.
- `prompts.context` usa el mismo `PromptEngine` sandbox que el system; un acceso bloqueado (SSTI) hace fallar la corrida. No lleva el bloque de `output_schema`.
- Regex de variables por query en el system: `\b(knowledge|prefetch)\b|memory\.(semantic|episodic)\b`.
- `cache.hit_ratio = round(cached_tokens / input_tokens, 3)`, 0 si `input_tokens` es 0.
- `turn_context.delivery` ∈ `message` | `system` | `none`.
- Line length 100; correr `uv run ruff check astromesh/ tests/` **y** `uv run ruff format --check astromesh/ tests/` antes de cada commit.
- Cada commit `feat:`/`fix:` lleva su entrada de `CHANGELOG.md` bajo `## [Unreleased]` en el mismo commit, sumando bullets a las subsecciones existentes (no duplicar encabezados).
- Commits en español; terminar el mensaje con una línea en blanco y `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Desvío deliberado del spec (registrado):** el spec nombra una lista `_PATTERNS_WITH_TURN_CONTEXT = {"react", "glyph"}` en el engine. El plan usa en su lugar un atributo de clase `consumes_turn_context = True` en `ReActPattern` y `GlyphPattern`, leído con `getattr(pattern, "consumes_turn_context", False)`. Motivo: un `pattern` desconocido cae a `ReActPattern` (`pattern_map.get(name, ReActPattern)`), y una lista por nombre lo mandaría al system aunque el objeto sí consuma el contexto. Sigue siendo un solo lugar de verdad.

## Review Focus

1. **Query multimodal con contexto en glyph:** el programa ve `query` aplanada (`_query_text`) y sin contexto; sólo los mensajes al modelo llevan el contexto — test en Task 1.
2. **Contexto que renderiza sólo whitespace** (todas las ramas `{% if %}` falsas): no se agrega nada y `delivery` es `none` — test en Task 2.
3. **Patrón desconocido en el YAML** (cae a ReAct): recibe el contexto como mensaje, no en el system — test en Task 2.
4. **Agente sin memoria conversacional con `prompts.context`**: el contexto viaja igual (no depende de `_history_messages`) — cubierto por el test de RAG de Task 2, que usa un agente con memoria; agregado un caso sin memoria en Task 2.
5. **`prompts.context` con `memory.conversation`**: no dispara el camino legado de historial (sólo mira `prompts.system`) — test en Task 2.

---

### Task 1: Patrones — `with_turn_context`, ReAct y Glyph

**Files:**
- Modify: `astromesh/orchestration/patterns.py` (helper nuevo; `ReActPattern` ~línea 35-40)
- Modify: `astromesh/orchestration/glyph_pattern.py` (`GlyphPattern`: atributo de clase; mensajes de la query en la generación ~línea 176-181 y en la narración ~línea 258-262)
- Test: `tests/test_turn_context.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces:
  - `with_turn_context(query, turn_context)` en `astromesh/orchestration/patterns.py` → query (str o list) con el contexto adelante.
  - `ReActPattern.consumes_turn_context = True`, `GlyphPattern.consumes_turn_context = True` (atributo de clase). `OrchestrationPattern` no lo define; el engine lee `getattr(pattern, "consumes_turn_context", False)`.
  - Los dos patrones leen `context.get("_turn_context")` (con el mismo guard `isinstance(context, dict)` que ya usan para `_history_messages`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_turn_context.py
from astromesh.orchestration.glyph_pattern import GlyphPattern
from astromesh.orchestration.patterns import ReActPattern, with_turn_context

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_parts",
            "description": "Busca repuestos",
            "parameters": {
                "type": "object",
                "properties": {"make": {"type": "string"}},
                "required": ["make"],
            },
        },
    }
]

PROGRAM = '```glyph\nv = search_parts(make="Toyota")\nreturn v\n```'


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None
        self.usage = {"input_tokens": 10, "output_tokens": 5}


class ScriptedModel:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    async def __call__(self, messages, tools, role=None):
        self.calls.append(messages)
        return FakeResponse(self._responses.pop(0))


async def _tool_fn(name, args):
    return [{"sku": "A"}]


def test_with_turn_context_string():
    assert with_turn_context("hola", "DOCS: x") == "DOCS: x\n\nhola"


def test_with_turn_context_multimodal():
    parts = [{"type": "text", "text": "mirá"}, {"type": "image_url", "image_url": {}}]
    assert with_turn_context(parts, "DOCS: x") == [{"type": "text", "text": "DOCS: x"}, *parts]


def test_with_turn_context_vacio_deja_la_query():
    assert with_turn_context("hola", None) == "hola"
    assert with_turn_context("hola", "") == "hola"
    parts = [{"type": "text", "text": "mirá"}]
    assert with_turn_context(parts, None) is parts


def test_los_patrones_declaran_que_consumen_el_contexto():
    assert ReActPattern.consumes_turn_context is True
    assert GlyphPattern.consumes_turn_context is True


async def test_react_antepone_el_contexto_al_ultimo_mensaje():
    model = ScriptedModel("listo")
    history = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}]
    await ReActPattern().execute(
        query="q",
        context={"_history_messages": history, "_turn_context": "DOCS: x"},
        model_fn=model,
        tool_fn=None,
        tools=[],
    )
    assert model.calls[0] == [*history, {"role": "user", "content": "DOCS: x\n\nq"}]


async def test_react_sin_contexto_no_cambia():
    model = ScriptedModel("listo")
    await ReActPattern().execute(
        query="q", context={}, model_fn=model, tool_fn=None, tools=[]
    )
    assert model.calls[0] == [{"role": "user", "content": "q"}]


async def test_glyph_lleva_el_contexto_en_la_query_y_en_la_narracion():
    sin = ScriptedModel(PROGRAM, "ok")
    await GlyphPattern().execute(
        query="necesito pastillas", context={}, model_fn=sin, tool_fn=_tool_fn, tools=TOOLS
    )
    con = ScriptedModel(PROGRAM, "ok")
    await GlyphPattern().execute(
        query="necesito pastillas",
        context={"_turn_context": "DOCS: x"},
        model_fn=con,
        tool_fn=_tool_fn,
        tools=TOOLS,
    )
    generacion = con.calls[0]
    # La gramática queda antes y sin tocar; sólo cambia el último mensaje.
    assert generacion[:-1] == sin.calls[0][:-1]
    assert generacion[-1] == {"role": "user", "content": "DOCS: x\n\nnecesito pastillas"}
    narracion = con.calls[1]
    assert narracion[0] == {"role": "user", "content": "DOCS: x\n\nnecesito pastillas"}


async def test_glyph_el_programa_ve_la_query_original():
    vistos = []

    async def tool_fn(name, args):
        vistos.append(args)
        return [{"sku": "A"}]

    async def explota(messages, tools, role=None):
        raise AssertionError("un programa fijo sin narración no llama al modelo")

    await GlyphPattern(program="v = search_parts(make=query)\nreturn v\n", narrate=False).execute(
        query=[{"type": "text", "text": "pastillas"}, {"type": "image_url", "image_url": {}}],
        context={"_caller_context": {}, "_turn_context": "DOCS: x"},
        model_fn=explota,
        tool_fn=tool_fn,
        tools=TOOLS,
    )
    assert vistos == [{"make": "pastillas"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_turn_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'with_turn_context'`.

- [ ] **Step 3: Implement**

En `astromesh/orchestration/patterns.py`, a nivel de módulo (antes de `class OrchestrationPattern`):

```python
def with_turn_context(query, turn_context):
    """La query del usuario con el contexto del turno adelante, o intacta si no hay.

    El contexto (`prompts.context`: RAG, prefetch) cambia en cada query, así que va
    al FINAL de la conversación, pegado al mensaje actual: todo lo anterior queda
    como prefijo estable para el caché del proveedor. Una query multimodal es una
    lista de partes; el contexto entra como una parte de texto más, adelante.
    """
    if not turn_context:
        return query
    if isinstance(query, list):
        return [{"type": "text", "text": turn_context}, *query]
    return f"{turn_context}\n\n{query}"
```

En `ReActPattern`:

```python
class ReActPattern(OrchestrationPattern):
    """Thought -> Action -> Observation loop."""

    consumes_turn_context = True

    async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
        history = context.get("_history_messages", []) if isinstance(context, dict) else []
        turn_context = context.get("_turn_context") if isinstance(context, dict) else None
        messages = [
            *list(history),
            {"role": "user", "content": with_turn_context(query, turn_context)},
        ]
```

(el resto del método no cambia).

En `astromesh/orchestration/glyph_pattern.py`: importar `with_turn_context` desde `astromesh.orchestration.patterns` (el módulo ya importa `OrchestrationPattern` de ahí; sumarlo a ese import). En `GlyphPattern`:

```python
class GlyphPattern(OrchestrationPattern):
    ...
    consumes_turn_context = True
```

En `execute`, junto a la línea que lee `history`:

```python
        turn_context = context.get("_turn_context") if isinstance(context, dict) else None
```

En la generación, reemplazar `{"role": "user", "content": query},` (el mensaje que sigue al bloque de gramática) por:

```python
                {"role": "user", "content": with_turn_context(query, turn_context)},
```

En la narración (`final = await model_fn([...])`), reemplazar `{"role": "user", "content": query},` por:

```python
                {"role": "user", "content": with_turn_context(query, turn_context)},
```

`env` no cambia: `env["query"]` sigue siendo `_query_text(query)`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_turn_context.py tests/test_glyph_pattern.py tests/test_patterns.py tests/test_glyph_engine.py -v`
Expected: todo PASS.

- [ ] **Step 5: CHANGELOG, lint, format, commit**

CHANGELOG, bajo `## [Unreleased]` → `### Added (Backend)`:

```markdown
- Patrones `react` y `glyph`: anteponen el contexto del turno (`_turn_context`) al mensaje del
  usuario actual, al final de la conversación, para que lo anterior sea prefijo cacheable.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/orchestration/patterns.py astromesh/orchestration/glyph_pattern.py tests/test_turn_context.py CHANGELOG.md
git commit -m "feat(orchestration): react y glyph anteponen el contexto del turno a la query"
```

---

### Task 2: Engine — `prompts.context`, entrega, presupuesto, warnings y `cache.hit_ratio`

**Files:**
- Modify: `astromesh/runtime/engine.py`:
  - helper de módulo nuevo `_per_query_vars_in(system_prompt)` junto a `_history_in_template` (~línea 139)
  - `_build_agent`: warnings al cargar (junto al warning de `_history_in_template`, ~línea 880) y `context_prompt=` en el `return Agent(...)` (~línea 1161)
  - `Agent.__init__`: parámetro `context_prompt=""`
  - `Agent.run`: bloque `prompt_render` / `context_fit` (~líneas 1576-1630)
  - `model_fn`: span `llm.complete` (~línea 1690, después de `cached_tokens`)
- Modify: `vscode-extension/schemas/agent.schema.json` (`properties.spec.properties.prompts.properties`)
- Test: `tests/test_context_budget_engine.py` (agregar al final; reusa `Fake`, `_t`, `_resp`, `_manifest`, `_agente`, `_capturar` y el fixture autouse `sin_litellm` que ya están ahí)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `with_turn_context`, `consumes_turn_context` (Task 1); `estimate_tokens` (ya importado en engine.py); `Agent._render_system(variables)` (existente; agrega `output_schema` — NO usar para el contexto).
- Produces: `Agent._context_prompt: str`; `memory_context["_turn_context"]`; span `context_fit` con `turn_context.tokens` y `turn_context.delivery`; span `llm.complete` con `cache.hit_ratio`.

- [ ] **Step 1: Write the failing tests** (agregar al final de `tests/test_context_budget_engine.py`)

```python
class FakeRAG:
    async def build_context(self, query_text):
        return f"DOC sobre {query_text}"


def _con_context(manifest, context="{% if knowledge %}DOCS: {{ knowledge }}{% endif %}", **kw):
    manifest["spec"]["prompts"]["context"] = context
    manifest["spec"].setdefault("orchestration", {}).update(kw)
    return manifest


def _span(result, name):
    return next(s for s in result["trace"]["spans"] if s["name"] == name)


async def test_contexto_va_en_el_ultimo_mensaje_y_el_system_queda_estable(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest()))
    agente._rag = FakeRAG()
    llamadas = _capturar(agente)
    r1 = await agente.run("frenos", session_id="s1")
    await agente.run("embrague", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "DOCS: DOC sobre frenos\n\nfrenos"}
    assert llamadas[1][-1] == {"role": "user", "content": "DOCS: DOC sobre embrague\n\nembrague"}
    assert llamadas[0][0] == llamadas[1][0]
    assert _span(r1, "context_fit")["attributes"]["turn_context.delivery"] == "message"
    assert _span(r1, "context_fit")["attributes"]["turn_context.tokens"] > 0


async def test_el_turno_persistido_es_la_query_original(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest()))
    agente._rag = FakeRAG()
    _capturar(agente)
    await agente.run("frenos", session_id="s1")
    persistidos = agente._memory._conversation.turns
    assert persistidos[0].role == "user"
    assert persistidos[0].content == "frenos"


async def test_contexto_sin_memoria_conversacional(tmp_path):
    manifest = _con_context(_manifest())
    del manifest["spec"]["memory"]
    agente = await _agente_sin_memoria(tmp_path, manifest)
    agente._rag = FakeRAG()
    llamadas = _capturar(agente)
    await agente.run("frenos", session_id="s1")
    assert llamadas[0][1:] == [{"role": "user", "content": "DOCS: DOC sobre frenos\n\nfrenos"}]


async def test_contexto_vacio_no_agrega_nada(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest()))  # sin RAG → knowledge vacío
    llamadas = _capturar(agente)
    r = await agente.run("frenos", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "frenos"}
    assert _span(r, "context_fit")["attributes"]["turn_context.delivery"] == "none"
    assert _span(r, "context_fit")["attributes"]["turn_context.tokens"] == 0


async def test_contexto_no_lleva_el_bloque_de_output_schema(tmp_path):
    manifest = _con_context(_manifest(), context="DOCS FIJOS")
    manifest["spec"]["output_schema"] = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
    }
    agente = await _agente(tmp_path, manifest)
    llamadas = _capturar(agente)
    await agente.run("frenos", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "DOCS FIJOS\n\nfrenos"}


async def test_patron_desconocido_cae_a_react_y_recibe_el_mensaje(tmp_path):
    agente = await _agente(tmp_path, _con_context(_manifest(), context="CTX", pattern="raro"))
    llamadas = _capturar(agente)
    await agente.run("frenos", session_id="s1")
    assert llamadas[0][-1] == {"role": "user", "content": "CTX\n\nfrenos"}


async def test_patron_sin_soporte_recibe_el_contexto_en_el_system(tmp_path, caplog):
    import logging

    from astromesh.orchestration.patterns import OrchestrationPattern

    with caplog.at_level(logging.WARNING):
        agente = await _agente(
            tmp_path, _con_context(_manifest(), context="CTX", pattern="plan_and_execute")
        )
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("mem-agent" in m and "prompts.context" in m for m in avisos), avisos

    visto = {}

    class Espia(OrchestrationPattern):
        async def execute(self, query, context, model_fn, tool_fn, tools, max_iterations=10):
            visto["context"] = context
            await model_fn([{"role": "user", "content": query}], [])
            return {"answer": "ok", "steps": []}

    agente._pattern = Espia()
    llamadas = _capturar(agente)
    r = await agente.run("frenos", session_id="s1")
    assert llamadas[0][0]["content"].endswith("\n\nCTX")
    assert "_turn_context" not in visto["context"]
    assert _span(r, "context_fit")["attributes"]["turn_context.delivery"] == "system"


async def test_tokens_del_contexto_achican_el_historial(tmp_path):
    model = {"primary": {"provider": "ollama", "model": "llama3", "context_window": 3000,
                         "max_tokens": 100}}
    turns = [_t("user" if i % 2 == 0 else "assistant", f"t{i:02d} " + "x" * 396) for i in range(40)]

    async def historial(context):
        agente = await _agente(
            tmp_path / context[:3], _con_context(_manifest(model=model, max_turns=40), context=context),
            turns=list(turns),
        )
        llamadas = _capturar(agente)
        await agente.run("q", session_id="s1")
        return len(llamadas[0]) - 2

    corto = await historial("CTX")
    largo = await historial("BIG" + "y" * 4000)
    assert largo < corto


async def test_contexto_con_memory_conversation_no_activa_el_camino_legado(tmp_path):
    ctx = "{% for t in memory.conversation %}{{ t.content }}{% endfor %}"
    agente = await _agente(
        tmp_path, _con_context(_manifest(), context=ctx), turns=[_t("user", "u1"), _t("assistant", "a1")]
    )
    llamadas = _capturar(agente)
    r = await agente.run("q", session_id="s1")
    assert _span(r, "context_fit")["attributes"]["history.delivery"] == "messages"
    assert llamadas[0][1] == {"role": "user", "content": "u1"}


async def test_warning_por_variables_de_query_en_el_system(tmp_path, caplog):
    import logging

    sistemas = {
        "rag": "Docs: {{ knowledge }}",
        "pref": "{{ prefetch.stock }}",
        "sem": "{{ memory.semantic }}",
        "kbid": "base {{ knowledge_base_id }}",
        "summ": "{{ memory.conversation_summary }}",
    }
    avisados = {}
    for clave, system in sistemas.items():
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            await _agente(tmp_path / clave, _manifest(system=system))
        avisados[clave] = any(
            "cambia en cada query" in r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        )
    assert avisados == {"rag": True, "pref": True, "sem": True, "kbid": False, "summ": False}


async def test_ssti_en_el_contexto_hace_fallar_la_corrida(tmp_path):
    from jinja2.exceptions import SecurityError

    agente = await _agente(tmp_path, _con_context(_manifest(), context="{{ ''.__class__.__mro__ }}"))
    _capturar(agente)
    with pytest.raises(SecurityError):
        await agente.run("q", session_id="s1")


async def test_cache_hit_ratio_en_el_span(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    usos = [
        {"input_tokens": 1000, "output_tokens": 5, "cache_read_input_tokens": 880},
        {"input_tokens": 0, "output_tokens": 5},
    ]

    async def route(messages, requirements=None, **kwargs):
        return CompletionResponse(
            content="ok", model="m", provider="p", usage=usos.pop(0), latency_ms=1.0, cost=0.0
        )

    agente._routers["default"].route = route
    r1 = await agente.run("q1", session_id="s1")
    r2 = await agente.run("q2", session_id="s1")
    assert _span(r1, "llm.complete")["attributes"]["cache.hit_ratio"] == 0.88
    assert _span(r2, "llm.complete")["attributes"]["cache.hit_ratio"] == 0
```

Y un helper más, junto a `_agente` (para el caso sin memoria — `_agente` asume `_memory._conversation`):

```python
async def _agente_sin_memoria(tmp_path, manifest):
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "mem-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "mem-agent" in runtime._agents, runtime._agent_errors
    return runtime._agents["mem-agent"]
```

Si `ruff format` deja líneas de más de 100 en los tests por strings, cortarlas por concatenación sin cambiar valores. `pytest` ya está importado en ese archivo (lo usa el fixture).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context_budget_engine.py -v`
Expected: los tests nuevos FAIL (el contexto no llega: `prompts.context` se ignora; falta `turn_context.*` en el span; falta `cache.hit_ratio`). Si `prompts.context` hace que el agente no cargue por el schema, eso también cuenta como RED esperado.

- [ ] **Step 3: Implement**

Schema — en `vscode-extension/schemas/agent.schema.json`, `properties.spec.properties.prompts.properties`, junto a `system`:

```json
"context": {
  "type": "string",
  "description": "Template Jinja de lo que cambia en cada turno (RAG, prefetch). Se antepone al mensaje del usuario actual para que system, tools e historial sean un prefijo estable para el caché del proveedor."
}
```

Helper de módulo en `engine.py`, junto a `_history_in_template`:

```python
def _per_query_vars_in(system_prompt: str | None) -> bool:
    """El system usa algo que cambia en cada query: rompe el prefijo del caché."""
    return (
        re.search(
            r"\b(knowledge|prefetch)\b|memory\.(semantic|episodic)\b", system_prompt or ""
        )
        is not None
    )
```

En `_build_agent`, después del warning de `_history_in_template`. El `pattern` ya está construido más abajo (`pattern = self._build_pattern(...)`), así que este bloque va **después** de esa línea:

```python
        prompts_spec = spec.get("prompts") or {}
        if _per_query_vars_in(prompts_spec.get("system")):
            logger.warning(
                "agent %r: el system prompt usa algo que cambia en cada query (knowledge, "
                "prefetch o memory.semantic/episodic): rompe el caché de prompts; movelo a "
                "`prompts.context`.",
                metadata["name"],
            )
        if prompts_spec.get("context") and not getattr(pattern, "consumes_turn_context", False):
            logger.warning(
                "agent %r: su patrón no separa `prompts.context`; va al final del system "
                "prompt y no hay ganancia de caché.",
                metadata["name"],
            )
```

En el `return Agent(...)`: `context_prompt=prompts.get("context") or "",`. En `Agent.__init__`, parámetro `context_prompt=""` (al final, con default) y `self._context_prompt = context_prompt`.

En `Agent.run`, dentro del bloque `prompt_render`, después del render base de `rendered_prompt` y antes de `fit_span = ...`:

```python
            # Lo que cambia por query (RAG, prefetch) va al final, pegado a la query:
            # system → tools → historial quedan como prefijo estable para el caché.
            # Mismo sandbox que el system; sin el bloque de output_schema.
            turn_context = ""
            if self._context_prompt:
                turn_context = self._prompt_engine.render(
                    self._context_prompt, variables
                ).strip()
            turn_context_tokens = estimate_tokens(turn_context)
```

En `base_tokens`, sumar `+ turn_context_tokens`.

Después de decidir la entrega del historial (después del `if history_in_template: ... else: ...`):

```python
            if not turn_context:
                turn_context_delivery = "none"
            elif getattr(self._pattern, "consumes_turn_context", False):
                memory_context["_turn_context"] = turn_context
                turn_context_delivery = "message"
            else:
                rendered_prompt = f"{rendered_prompt}\n\n{turn_context}"
                turn_context_delivery = "system"
```

Y en el dict de atributos de `fit_span` agregar:

```python
                "turn_context.tokens": turn_context_tokens,
                "turn_context.delivery": turn_context_delivery,
```

Ojo: `variables["memory"]` es `memory_context`; el `_turn_context` se escribe después de todos los renders, así que ningún template lo ve.

En `model_fn`, dentro del `if hasattr(response, "usage") and response.usage:`, después del `set_attribute("cached_tokens", ...)`:

```python
                        input_tokens = response.usage.get("input_tokens", 0) or 0
                        cached = response.usage.get("cache_read_input_tokens", 0) or 0
                        # La métrica de si el prefijo estable está pegando en el caché.
                        llm_span.set_attribute(
                            "cache.hit_ratio",
                            round(cached / input_tokens, 3) if input_tokens else 0,
                        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_context_budget_engine.py tests/test_turn_context.py tests/test_agent_schema.py -v`
Expected: PASS.

Run: `uv run pytest -q`
Expected: suite completa verde. Si un test existente se rompe, leerlo antes de tocarlo y reportarlo; no debilitar asserts.

- [ ] **Step 5: CHANGELOG, lint, format, commit**

CHANGELOG, bajo `## [Unreleased]`:

```markdown
### Added (Backend)
- **`prompts.context`**: template opcional para lo que cambia en cada turno (RAG, prefetch).
  Se antepone al mensaje del usuario actual, así system, tools e historial quedan como
  prefijo estable y el caché automático del proveedor (Kimi/Moonshot) los sirve. El turno
  guardado en memoria sigue siendo la query original. Con patrones que no lo separan
  (`plan_and_execute`, etc.) va al final del system, con un warning al cargar.
- Warning al cargar cuando `prompts.system` usa `knowledge`, `prefetch` o
  `memory.semantic`/`episodic`: rompe el caché; moverlo a `prompts.context`.
- `cache.hit_ratio` en el span `llm.complete` (`cached_tokens / input_tokens`).
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py vscode-extension/schemas/agent.schema.json tests/test_context_budget_engine.py CHANGELOG.md
git commit -m "feat(runtime): prompts.context — lo que cambia por query va al final y el prefijo queda cacheable"
```

---

### Task 3: Guía de configuración y verificación final

**Files:**
- Modify: `docs/CONFIGURATION_GUIDE.md` (sección de prompts; buscar con `grep -n "prompts" docs/CONFIGURATION_GUIDE.md` la tabla o el bloque que documenta `prompts.system`)

- [ ] **Step 1: Guía**

Agregar, debajo de donde se documenta `prompts.system`:

````markdown
**`prompts.context` — lo que cambia en cada turno.** Todo lo que depende de la query (RAG,
`prefetch`) va acá y no en `prompts.system`. El runtime lo antepone al mensaje del usuario
actual, así el prompt queda en este orden:

system → tools → historial → **contexto + query**

Todo lo anterior al último mensaje es idéntico entre llamadas, y el caché automático del
proveedor (Kimi/Moonshot, OpenAI, vLLM) lo sirve a precio reducido. Si el system usa
`knowledge` o `prefetch`, cambia en cada query y no se cachea nada: el runtime lo avisa al
cargar el agente.

```yaml
prompts:
  system: |
    Sos Lucía, analista comercial. Respondé con los datos que te paso.
  context: |
    {% if knowledge %}DOCUMENTOS RELEVANTES:
    {{ knowledge }}{% endif %}
    {% if prefetch.stock %}STOCK ACTUAL: {{ prefetch.stock }}{% endif %}
```

El turno que se guarda en memoria es la query original, sin el contexto. Los patrones
`react` y `glyph` lo separan; con los demás va al final del system prompt. El span
`llm.complete` trae `cache.hit_ratio` para medir si el caché está pegando.
````

- [ ] **Step 2: Verificación completa**

```bash
uv run pytest -q
uv run ruff check astromesh/ tests/
uv run ruff format --check astromesh/ tests/
```

Expected: todo verde. Revisar que `## [Unreleased]` del CHANGELOG no tenga encabezados duplicados (fusionar si los hay, sin cambiar bullets).

- [ ] **Step 3: Commit**

```bash
git add docs/CONFIGURATION_GUIDE.md CHANGELOG.md
git commit -m "docs: guía de configuración — prompts.context y el orden del prompt para el caché"
```

- [ ] **Step 4: Seguimiento fuera del repo** — anotar en el reporte (no implementar): generador de Cortex/Nexus (sacar `memory.conversation` del system de OFFICIUM y mover "LOS DOCUMENTOS" a `prompts.context`) y schema de Cortex (`prompts.context`, `context_window`).
