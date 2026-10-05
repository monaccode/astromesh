# Contexto conversacional con presupuesto real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `spec.memory.conversational` funcione de verdad: turnos con tokens contados, presupuesto derivado de la ventana del modelo, resumen cableado, e historial entregado como mensajes (prefijo estable para el caché).

**Architecture:** Un módulo nuevo `astromesh/core/tokens.py` cuenta tokens y resuelve la ventana del modelo, sin dependencias nuevas (usa litellm sólo si está instalado). `MemoryManager` carga los conteos, el resumen y expone `fit_history()`. `Agent.run` mide la base (system + tools + respuesta), recorta el historial al presupuesto y lo entrega como `_history_messages`, o por el template legado si el system prompt usa `memory.conversation`.

**Tech Stack:** Python 3.12, pytest (asyncio auto), Jinja2 sandbox, litellm opcional.

**Spec:** `docs/superpowers/specs/2026-10-05-context-budget-fix-design.md`

## Global Constraints

- `astromesh/api/main.py` tiene que importar **sin extras**: nada de `import litellm` a nivel de módulo; siempre perezoso y tolerante a `ImportError`.
- Ningún paso de contexto hace fallar una corrida (mismo criterio que `agent_rag.build_context`).
- Ventana por defecto: `32_000`. Margen: el presupuesto usa `int(ventana * 0.9)`. Respuesta por defecto: `1024` tokens si el candidato no declara `max_tokens`.
- Estimación sin litellm: `ceil(len(text) / 4)`.
- Prefijo del mensaje de resumen: `[Resumen de la conversación anterior]`.
- Line length 100; correr `uv run ruff check astromesh/ tests/` **y** `uv run ruff format --check astromesh/ tests/` antes de cada commit (CI corre los dos).
- Commits convencionales en español, como el resto del repo. **Cada commit `feat:`/`fix:` lleva su entrada de `CHANGELOG.md` bajo `## [Unreleased]` en el mismo commit** (regla del CLAUDE.md; usar `/changelog-automation`). Cada tarea dice qué línea agrega.
- En los tests, litellm **está instalado** en el venv de dev: todo test que compare conteos exactos parchea `astromesh.core.tokens._litellm` para que devuelva `None`.

## Review Focus

1. **Historial recortado que empieza con un turno `assistant`**: cuando el presupuesto corta en medio de un par, el primer mensaje no debe ser del asistente (algunos proveedores exigen que el primero sea `user`). Se descartan los `assistant` iniciales — test en Task 4.
2. **El resumen solo no entra en el presupuesto**: se descarta el resumen, no se lanza nada — test en Task 2.
3. **Memoria semántica empieza a guardarse**: `persist_turn` guarda en la semántica sólo si `token_count > 50`; con conteos reales eso empieza a ocurrir para agentes que tengan semántica cableada (hoy el engine no la cablea; el ADK podría). Va en el CHANGELOG — Task 2.
4. **Resumen en cada turno**: con `strategy: summary`, una vez superado `max_turns` se resume en cada `persist_turn` (comportamiento existente del disparador, ahora vivo). Costo de una llamada al rol `summarizer` por turno. Documentado en el CHANGELOG; acotarlo queda para el subproyecto 2.
5. **Patrones que no leen `_history_messages`** (PlanAndExecute, ParallelFanOut, Pipeline, Supervisor, Swarm): siguen sin historial por mensajes, igual que hoy. No es regresión; queda anotado en el CHANGELOG.

---

### Task 1: `astromesh/core/tokens.py` — conteo y ventana

**Files:**
- Create: `astromesh/core/tokens.py`
- Test: `tests/test_tokens.py`

**Interfaces:**
- Produces:
  - `estimate_tokens(text: str | None) -> int`
  - `resolve_context_window(candidates: list[dict]) -> tuple[int, str]` — fuente ∈ `"yaml" | "ollama.num_ctx" | "litellm" | "default"`
  - `DEFAULT_CONTEXT_WINDOW = 32_000`
  - `_litellm() -> module | None` (punto de parcheo en tests)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tokens.py
import types

import pytest

from astromesh.core import tokens
from astromesh.core.tokens import DEFAULT_CONTEXT_WINDOW, estimate_tokens, resolve_context_window


@pytest.fixture
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _fake_litellm(max_input=None, count=None, falla=False):
    def get_model_info(model):
        if falla or max_input is None:
            raise Exception("modelo desconocido")
        return {"max_input_tokens": max_input}

    def token_counter(model="", text=""):
        if falla:
            raise Exception("tokenizer roto")
        return count

    return types.SimpleNamespace(get_model_info=get_model_info, token_counter=token_counter)


def test_estimate_sin_litellm_es_len_sobre_4(sin_litellm):
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_estimate_usa_litellm_si_esta(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(count=7))
    assert estimate_tokens("hola mundo") == 7


def test_estimate_cae_a_len_si_litellm_falla(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(falla=True))
    assert estimate_tokens("abcdefgh") == 2


def test_ventana_yaml_gana(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(max_input=128_000))
    cand = {"provider": "ollama", "model": "x", "context_window": 8000,
            "parameters": {"num_ctx": 4096}}
    assert resolve_context_window([cand]) == (8000, "yaml")


def test_ventana_num_ctx_de_ollama(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(max_input=128_000))
    cand = {"source": "ollama", "model": "x", "parameters": {"num_ctx": 4096}}
    assert resolve_context_window([cand]) == (4096, "ollama.num_ctx")


def test_ventana_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(max_input=128_000))
    assert resolve_context_window([{"provider": "openai", "model": "gpt-4o"}]) == (
        128_000,
        "litellm",
    )


def test_ventana_default(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: _fake_litellm(falla=True))
    assert resolve_context_window([{"provider": "openai", "model": "raro"}]) == (
        DEFAULT_CONTEXT_WINDOW,
        "default",
    )
    assert resolve_context_window([]) == (DEFAULT_CONTEXT_WINDOW, "default")


def test_ventana_es_la_minima_entre_candidatos(sin_litellm):
    cands = [
        {"provider": "openai", "model": "a", "context_window": 200_000},
        {"provider": "ollama", "model": "b", "parameters": {"num_ctx": 32_768}},
    ]
    assert resolve_context_window(cands) == (32_768, "ollama.num_ctx")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.core.tokens'`

- [ ] **Step 3: Implement**

```python
# astromesh/core/tokens.py
"""Conteo de tokens y ventana de contexto, sin dependencias nuevas.

litellm es un extra opcional: se importa perezoso y cualquier falla cae al
estimador `len/4`. `astromesh/api/main.py` tiene que seguir importando sin
extras o la imagen de astromesh-os no bootea.
"""

import logging
import math

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 32_000


def _litellm():
    try:
        import litellm
    except ImportError:
        return None
    return litellm


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    lib = _litellm()
    if lib is not None:
        try:
            return int(lib.token_counter(text=text))
        except Exception:  # noqa: BLE001 — cualquier falla cae al estimador
            logger.debug("litellm.token_counter falló; uso len/4", exc_info=True)
    return math.ceil(len(text) / 4)


def _candidate_window(block: dict) -> tuple[int, str] | None:
    if block.get("context_window"):
        return int(block["context_window"]), "yaml"
    if (block.get("source") or block.get("provider")) == "ollama":
        num_ctx = (block.get("parameters") or {}).get("num_ctx")
        if num_ctx:
            return int(num_ctx), "ollama.num_ctx"
    lib = _litellm()
    if lib is not None and block.get("model"):
        try:
            n = lib.get_model_info(block["model"]).get("max_input_tokens")
            if n:
                return int(n), "litellm"
        except Exception:  # noqa: BLE001 — modelo desconocido para litellm
            logger.debug("litellm no conoce %r", block.get("model"), exc_info=True)
    return None


def resolve_context_window(candidates: list[dict]) -> tuple[int, str]:
    """La ventana MÍNIMA entre candidatos: un fallback chico no debe desbordar."""
    found = [w for w in map(_candidate_window, candidates) if w]
    if not found:
        return DEFAULT_CONTEXT_WINDOW, "default"
    return min(found)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tokens.py -v`
Expected: 8 passed

- [ ] **Step 5: Lint, format, commit**

```bash
uv run ruff check astromesh/core/tokens.py tests/test_tokens.py
uv run ruff format astromesh/core/tokens.py tests/test_tokens.py
git add astromesh/core/tokens.py tests/test_tokens.py CHANGELOG.md
git commit -m "feat(core): tokens.py — estimate_tokens y resolve_context_window sin dependencias nuevas"
```

CHANGELOG, bajo `## [Unreleased]` → `### Added (Backend)` (crear la sección si no existe):

```markdown
- `astromesh/core/tokens.py`: conteo de tokens (litellm si está instalado, si no `len/4`) y
  resolución de la ventana de contexto del modelo, sin dependencias nuevas en el core.
```

---

### Task 2: `MemoryManager` — conteos, resumen y `fit_history`; borrar código muerto

**Files:**
- Modify: `astromesh/core/memory.py` (`build_context`, `persist_turn`, nuevo `fit_history`, logger)
- Modify: `astromesh/memory/strategies/token_budget.py` (fallback a `estimate_tokens`)
- Delete: `astromesh/memory/strategies/sliding_window.py`, `astromesh/memory/strategies/summary.py`
- Modify: `tests/test_memory_backends.py` (borrar `test_sliding_window`, `test_sliding_window_under_limit`, `test_summary_strategy`, `test_summary_strategy_short_history`)
- Test: `tests/test_memory_budget.py`

**Interfaces:**
- Consumes: `estimate_tokens` (Task 1)
- Produces:
  - `MemoryManager.build_context(session_id, current_query, max_tokens=None) -> dict` — ya **no** recorta salvo que se pase `max_tokens`; con `strategy: summary` agrega `context["conversation_summary"]`. Firma compatible con el ADK (`memory.build_context(session_id, query)`).
  - `MemoryManager.fit_history(context: dict, budget: int) -> dict` — muta `context["conversation"]` (y `conversation_summary`) y devuelve `{"turns_kept": int, "turns_dropped": int, "tokens": int, "summary_used": bool}`.
  - `persist_turn` completa `turn.token_count` si es 0, y atrapa fallas de `summarize_fn`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_memory_budget.py
from datetime import UTC, datetime

import pytest

from astromesh.core import tokens
from astromesh.core.memory import ConversationBackend, ConversationTurn, MemoryManager


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _t(role, content, n=0):
    return ConversationTurn(role=role, content=content, timestamp=datetime.now(UTC), token_count=n)


class Fake(ConversationBackend):
    def __init__(self, turns=None, summary=None):
        self.turns = list(turns or [])
        self.summary = summary
        self.saved_summary = None

    async def save_turn(self, session_id, turn):
        self.turns.append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self.turns[-limit:])

    async def clear(self, session_id):
        self.turns = []

    async def get_summary(self, session_id):
        return self.summary

    async def save_summary(self, session_id, summary):
        self.saved_summary = summary


async def test_persist_carga_token_count():
    backend = Fake()
    mgr = MemoryManager("a", {"conversational": {}}, conversation=backend)
    await mgr.persist_turn("s", _t("user", "x" * 40))
    await mgr.persist_turn("s", _t("assistant", "y" * 80))
    assert [t.token_count for t in backend.turns] == [10, 20]


async def test_build_context_estima_filas_viejas_con_cero():
    backend = Fake([_t("user", "x" * 40, n=0)])
    mgr = MemoryManager("a", {"conversational": {}}, conversation=backend)
    ctx = await mgr.build_context("s", "q")
    assert ctx["conversation"][0].token_count == 10


async def test_token_budget_recorta_y_se_queda_con_lo_ultimo():
    turns = [_t("user" if i % 2 == 0 else "assistant", f"{i:02d}" + "x" * 398) for i in range(40)]
    mgr = MemoryManager(
        "a", {"conversational": {"strategy": "token_budget"}}, conversation=Fake(turns)
    )
    ctx = await mgr.build_context("s", "q")
    stats = mgr.fit_history(ctx, 1000)  # 100 tokens por turno → entran 10
    assert stats["turns_kept"] == 10
    assert stats["turns_dropped"] == 30
    assert ctx["conversation"][-1] is turns[-1]


async def test_build_context_sin_presupuesto_no_recorta():
    turns = [_t("user", "x" * 400) for _ in range(30)]
    mgr = MemoryManager(
        "a", {"conversational": {"strategy": "token_budget"}}, conversation=Fake(turns)
    )
    ctx = await mgr.build_context("s", "q")
    assert len(ctx["conversation"]) == 30


async def test_summary_carga_el_resumen_y_lo_cuenta():
    turns = [_t("user", "x" * 400) for _ in range(5)]
    mgr = MemoryManager(
        "a",
        {"conversational": {"strategy": "summary"}},
        conversation=Fake(turns, summary="z" * 400),
    )
    ctx = await mgr.build_context("s", "q")
    stats = mgr.fit_history(ctx, 300)  # 100 del resumen + 2 turnos de 100
    assert ctx["conversation_summary"] == "z" * 400
    assert stats["summary_used"] is True
    assert stats["turns_kept"] == 2


async def test_resumen_que_no_entra_se_descarta_sin_lanzar():
    mgr = MemoryManager(
        "a",
        {"conversational": {"strategy": "summary"}},
        conversation=Fake([_t("user", "x" * 40)], summary="z" * 4000),
    )
    ctx = await mgr.build_context("s", "q")
    stats = mgr.fit_history(ctx, 50)
    assert ctx["conversation_summary"] is None
    assert stats["summary_used"] is False
    assert stats["turns_kept"] == 1


async def test_presupuesto_cero_deja_historial_vacio():
    mgr = MemoryManager("a", {"conversational": {}}, conversation=Fake([_t("user", "hola")]))
    ctx = await mgr.build_context("s", "q")
    assert mgr.fit_history(ctx, 0)["turns_kept"] == 0
    assert ctx["conversation"] == []


async def test_falla_del_resumen_no_rompe_persist():
    async def explota(turns):
        raise RuntimeError("rol caído")

    backend = Fake([_t("user", "x") for _ in range(30)])
    mgr = MemoryManager(
        "a", {"conversational": {"max_turns": 20}}, conversation=backend, summarize_fn=explota
    )
    await mgr.persist_turn("s", _t("user", "y"))  # no lanza
    assert backend.saved_summary is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_memory_budget.py -v`
Expected: FAIL — `test_persist_carga_token_count` (`[0, 0]`), `AttributeError: 'MemoryManager' object has no attribute 'fit_history'`, `RuntimeError: rol caído`.

- [ ] **Step 3: Implement in `astromesh/core/memory.py`**

Agregar arriba:

```python
import logging
...
from astromesh.core.tokens import estimate_tokens

logger = logging.getLogger(__name__)
```

Reemplazar `build_context` completo por:

```python
    async def build_context(self, session_id, current_query, max_tokens=None):
        """Historial + semántica + episódica. Recorta el historial sólo si se pasa
        `max_tokens`; el engine recorta después con `fit_history`, cuando ya midió
        el system prompt y las tools."""
        context = {"conversation": [], "semantic": [], "episodic": []}

        if self._conversation:
            conv = self.config.get("conversational", {})
            strategy = conv.get("strategy", "sliding_window")
            if strategy == "token_budget":
                turns = await self._conversation.get_history(session_id)
            else:
                turns = await self._conversation.get_history(
                    session_id, limit=conv.get("max_turns", 50)
                )
            # Filas anteriores a este fix tienen token_count=0: se estiman al leer.
            for turn in turns:
                if not turn.token_count:
                    turn.token_count = estimate_tokens(turn.content)
            context["conversation"] = list(turns)
            if strategy == "summary":
                context["conversation_summary"] = await self._conversation.get_summary(
                    session_id
                )
            if max_tokens is not None:
                self.fit_history(context, max_tokens)

        if self._semantic and self._embed:
            query_emb = await self._embed(current_query)
            threshold = self.config.get("semantic", {}).get("similarity_threshold", 0.75)
            max_results = self.config.get("semantic", {}).get("max_results", 10)
            context["semantic"] = await self._semantic.search(
                self.agent_id, query_emb, top_k=max_results, threshold=threshold
            )

        if self._episodic:
            context["episodic"] = await self._episodic.recall(self.agent_id, limit=5)

        return context

    def fit_history(self, context, budget):
        """Recorta `context["conversation"]` (y el resumen) a `budget` tokens.

        El resumen se cuenta primero; si solo no entra, se descarta. Los turnos
        se eligen de lo más nuevo a lo más viejo con TokenBudgetStrategy.
        """
        from astromesh.memory.strategies.token_budget import TokenBudgetStrategy

        turns = context.get("conversation") or []
        summary = context.get("conversation_summary")
        summary_tokens = estimate_tokens(summary)
        if summary_tokens > budget:
            context["conversation_summary"] = summary = None
            summary_tokens = 0
        kept = TokenBudgetStrategy().apply(turns, budget=max(0, budget - summary_tokens))
        context["conversation"] = kept
        return {
            "turns_kept": len(kept),
            "turns_dropped": len(turns) - len(kept),
            "tokens": summary_tokens + sum(t.token_count for t in kept),
            "summary_used": bool(summary),
        }
```

(El import de `TokenBudgetStrategy` va adentro de la función: `token_budget.py` importa `ConversationTurn` de este módulo.)

En `persist_turn`, reemplazar el bloque `if self._conversation:` por:

```python
        if self._conversation:
            if not turn.token_count:
                turn.token_count = estimate_tokens(turn.content)
            await self._conversation.save_turn(session_id, turn)
            history = await self._conversation.get_history(session_id)
            max_turns = self.config.get("conversational", {}).get("max_turns", 50)
            if len(history) > max_turns and self._summarize:
                try:
                    summary = await self._summarize(history[:-10])
                    await self._conversation.save_summary(session_id, summary)
                except Exception:  # noqa: BLE001 — la respuesta ya se entregó
                    logger.warning(
                        "memory.summary falló para agent=%s session=%s; queda el resumen anterior",
                        self.agent_id,
                        session_id,
                        exc_info=True,
                    )
```

- [ ] **Step 4: `token_budget.py` fallback y borrar código muerto**

En `astromesh/memory/strategies/token_budget.py`, en la ruta Python reemplazar:

```python
            cost = turn.token_count if turn.token_count > 0 else len(turn.content.split())
```

por:

```python
            cost = turn.token_count if turn.token_count > 0 else estimate_tokens(turn.content)
```

y agregar `from astromesh.core.tokens import estimate_tokens` en los imports.

```bash
git rm astromesh/memory/strategies/sliding_window.py astromesh/memory/strategies/summary.py
```

En `tests/test_memory_backends.py` borrar las cuatro funciones `test_sliding_window`, `test_sliding_window_under_limit`, `test_summary_strategy`, `test_summary_strategy_short_history` (importan los módulos borrados). Verificar que `astromesh/memory/strategies/__init__.py` no los reexporte: `grep -n "sliding_window\|summary" astromesh/memory/strategies/__init__.py` debe salir vacío; si no, quitar esas líneas.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_memory_budget.py tests/test_memory.py tests/test_memory_backends.py tests/test_native_tokens.py -v`
Expected: todo PASS.

- [ ] **Step 6: CHANGELOG, lint, format, commit**

CHANGELOG, bajo `## [Unreleased]`:

```markdown
### Fixed
- **Memoria conversacional: los turnos se guardan con `token_count`** (antes siempre 0, así
  que `token_budget` metía el historial entero). Las filas viejas se estiman al leerlas.
  Una falla del resumen ya no rompe `persist_turn`.

### Changed
- Con conteos reales, `persist_turn` guarda en la memoria semántica las respuestas de más de
  50 tokens cuando el agente tiene semántica cableada (antes nunca ocurría).

### Removed
- `astromesh/memory/strategies/sliding_window.py` y `summary.py`: no los usaba nadie.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add -A astromesh/core/memory.py astromesh/memory/strategies/ tests/test_memory_budget.py tests/test_memory_backends.py CHANGELOG.md
git commit -m "fix(memory): contar tokens de los turnos, cargar el resumen y recortar con fit_history"
```

---

### Task 3: Engine al cargar — ventana, respuesta, resumidor, schema

**Files:**
- Modify: `astromesh/runtime/engine.py` — `_SELECTOR_KEYS` (~línea 256), `_build_agent` (~línea 779-800 y el `return Agent(...)` ~1073), `Agent.__init__` (~1314), helper nuevo `_summarizer` a nivel de módulo
- Modify: `vscode-extension/schemas/agent.schema.json` — `$defs/modelConfig.properties`
- Test: `tests/test_context_budget_engine.py` (se crea acá; Task 4 lo extiende)

**Interfaces:**
- Consumes: `resolve_context_window`, `estimate_tokens` (Task 1); `MemoryManager(..., summarize_fn=...)` (existente)
- Produces:
  - `Agent.__init__(..., context_window: int = DEFAULT_CONTEXT_WINDOW, context_window_source: str = "default", response_tokens: int = 1024)` → atributos `_context_window`, `_context_window_source`, `_response_tokens`
  - `_summarizer(routers: dict) -> Callable[[list[ConversationTurn]], Awaitable[str]]`
  - `DEFAULT_RESPONSE_TOKENS = 1024` en `engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_context_budget_engine.py
from datetime import UTC, datetime

import pytest
import yaml

from astromesh.core import tokens
from astromesh.core.memory import ConversationBackend, ConversationTurn
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


class Fake(ConversationBackend):
    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.summary = None

    async def save_turn(self, session_id, turn):
        self.turns.append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self.turns[-limit:])

    async def clear(self, session_id):
        self.turns = []

    async def get_summary(self, session_id):
        return self.summary

    async def save_summary(self, session_id, summary):
        self.summary = summary


def _t(role, content):
    return ConversationTurn(role=role, content=content, timestamp=datetime.now(UTC))


def _resp(content="ok"):
    return CompletionResponse(
        content=content, model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0
    )


def _manifest(system="sos un agente", strategy="sliding_window", model=None, **conv):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "mem-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": model or {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": system},
            "memory": {
                "conversational": {
                    "backend": "redis",
                    "connection": {"url": "redis://localhost:1"},
                    "strategy": strategy,
                    **conv,
                }
            },
        },
    }


async def _agente(tmp_path, manifest, turns=None):
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "agents" / "mem-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    runtime = AgentRuntime(config_dir=str(config_dir))
    await runtime.bootstrap()
    assert "mem-agent" in runtime._agents, runtime._agent_errors
    agente = runtime._agents["mem-agent"]
    agente._memory._conversation = Fake(turns)
    return agente


def _capturar(agente):
    """Reemplaza el router default; devuelve la lista de `messages` de cada llamada."""
    llamadas = []

    async def route(messages, requirements=None, **kwargs):
        llamadas.append(messages)
        return _resp()

    agente._routers["default"].route = route
    return llamadas


async def test_ventana_desde_yaml_y_minima_entre_candidatos(tmp_path):
    model = {
        "default": {
            "candidates": [
                {"provider": "ollama", "model": "a", "context_window": 200_000},
                {"provider": "ollama", "model": "b", "context_window": 8_000},
            ]
        }
    }
    agente = await _agente(tmp_path, _manifest(model=model))
    assert agente._context_window == 8_000
    assert agente._context_window_source == "yaml"


async def test_ventana_default_y_respuesta_desde_max_tokens(tmp_path):
    model = {"primary": {"provider": "ollama", "model": "llama3", "max_tokens": 777}}
    agente = await _agente(tmp_path, _manifest(model=model))
    assert agente._context_window == tokens.DEFAULT_CONTEXT_WINDOW
    assert agente._context_window_source == "default"
    assert agente._response_tokens == 777


async def test_summary_usa_el_rol_summarizer(tmp_path):
    model = {
        "default": {"candidates": [{"provider": "ollama", "model": "grande"}]},
        "roles": {"summarizer": {"candidates": [{"provider": "ollama", "model": "chico"}]}},
    }
    agente = await _agente(
        tmp_path,
        _manifest(model=model, strategy="summary", max_turns=4),
        turns=[_t("user", f"m{i}") for i in range(12)],
    )
    pedidos = []

    async def route(messages, requirements=None, **kwargs):
        pedidos.append(messages)
        return _resp("RESUMEN")

    agente._routers["summarizer"].route = route
    await agente._memory.persist_turn("s1", _t("user", "otro"))
    assert len(pedidos) == 1
    assert "m0" in pedidos[0][-1]["content"]
    assert agente._memory._conversation.summary == "RESUMEN"


async def test_sin_strategy_summary_no_se_cablea_resumidor(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    assert agente._memory._summarize is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context_budget_engine.py -v`
Expected: FAIL — `AttributeError: 'Agent' object has no attribute '_context_window'`; el YAML con `context_window` además dispara el warning de clave ignorada.

- [ ] **Step 3: Implement**

En `engine.py`, imports:

```python
from astromesh.core.tokens import DEFAULT_CONTEXT_WINDOW, estimate_tokens, resolve_context_window
```

`_SELECTOR_KEYS` — `context_window` la lee el runtime para todas las fuentes, no el provider, así que no debe disparar `_warn_unconsumed_keys`:

```python
# `context_window` no lo consume el provider sino el runtime (presupuesto del
# historial, `core/tokens.py`), para cualquier fuente.
_SELECTOR_KEYS = frozenset({"source", "provider", "model", "providerRef", "context_window"})
```

Constantes y helper a nivel de módulo (junto a `_model_parameters`):

```python
DEFAULT_RESPONSE_TOKENS = 1024

_SUMMARY_PROMPT = (
    "Resumí la conversación que sigue en pocas líneas. Conservá nombres, datos, "
    "cifras, pedidos y compromisos; descartá saludos y relleno. Respondé sólo el resumen."
)


def _summarizer(routers: dict):
    """`summarize_fn` de MemoryManager: el rol `summarizer` si existe, si no `default`."""
    router = routers.get("summarizer") or routers["default"]

    async def summarize(turns):
        texto = "\n".join(f"[{t.role}] {t.content}" for t in turns)
        response = await router.route(
            [{"role": "system", "content": _SUMMARY_PROMPT}, {"role": "user", "content": texto}]
        )
        return response.content

    return summarize
```

En `_build_agent`, reemplazar la construcción de `memory` (bloque `memory = MemoryManager(...)`, conservando el comentario largo de arriba) por:

```python
        conv_spec = memory_spec.get("conversational") or {}
        memory = MemoryManager(
            agent_id=metadata["name"],
            config=memory_spec,
            conversation=self._conversation_backend(metadata["name"], memory_spec),
            # Sólo con `strategy: summary`: resumir es una llamada al modelo por
            # turno, y un agente que no la pidió no la paga.
            summarize_fn=_summarizer(routers) if conv_spec.get("strategy") == "summary" else None,
        )
        default_candidates = [
            resolve_block(b, self._provider_registry)
            for b in self._normalize_model_spec(model_spec)["default"]["candidates"]
        ]
        context_window, context_window_source = resolve_context_window(default_candidates)
        if context_window_source == "default":
            logger.warning(
                "agent %r: no pude determinar la ventana de contexto del modelo; uso %d "
                "tokens. Declará `context_window` en el candidato.",
                metadata["name"],
                context_window,
            )
        primary = default_candidates[0] if default_candidates else {}
        response_tokens = int(
            (_model_parameters(primary) or {}).get("max_tokens") or DEFAULT_RESPONSE_TOKENS
        )
        if conv_spec and "memory.conversation" in (spec.get("prompts") or {}).get("system", ""):
            logger.warning(
                "agent %r: historial en el system prompt (`memory.conversation`): rompe el "
                "caché de prompts; migrá a mensajes quitándolo del template.",
                metadata["name"],
            )
```

En el `return Agent(...)` agregar:

```python
            context_window=context_window,
            context_window_source=context_window_source,
            response_tokens=response_tokens,
```

En `Agent.__init__` agregar los parámetros (al final, con default para que los tests que construyen `Agent(...)` a mano sigan andando) y guardarlos:

```python
        context_window=DEFAULT_CONTEXT_WINDOW,
        context_window_source="default",
        response_tokens=DEFAULT_RESPONSE_TOKENS,
    ):
        ...
        self._context_window = context_window
        self._context_window_source = context_window_source
        self._response_tokens = response_tokens
```

Schema — en `vscode-extension/schemas/agent.schema.json`, dentro de `$defs.modelConfig.properties`, junto a `max_tokens`:

```json
"context_window": {
  "type": "integer",
  "minimum": 1,
  "description": "Tokens de entrada que acepta el modelo. Fija el presupuesto del historial conversacional. Sin esto: num_ctx (Ollama), litellm, o 32000."
},
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_context_budget_engine.py tests/test_agent_schema.py tests/test_engine_role_routers.py tests/test_engine.py -v`
Expected: PASS.

- [ ] **Step 5: CHANGELOG, lint, format, commit**

CHANGELOG, bajo `## [Unreleased]`:

```markdown
### Added (Backend)
- `context_window` en el candidato del modelo: fija la ventana de contexto. Sin él se usa
  `num_ctx` (Ollama), lo que sepa litellm, o 32000 con un warning. Con varios candidatos
  gana la más chica.

### Fixed
- **`strategy: summary` resume de verdad**, con el rol `summarizer` del agente (o `default`).
  Una vez superado `max_turns` resume en cada turno: una llamada al modelo por turno.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py vscode-extension/schemas/agent.schema.json tests/test_context_budget_engine.py CHANGELOG.md
git commit -m "fix(runtime): ventana de contexto por candidato y resumidor cableado al rol summarizer"
```

---

### Task 4: Engine en la corrida — presupuesto, recorte y entrega como mensajes

**Files:**
- Modify: `astromesh/runtime/engine.py` — `Agent.run` (bloque `memory_build` ~1404-1408 y `prompt_render` ~1469-1485), nuevo método `Agent._render_system`, nuevo helper de módulo `_history_messages`
- Test: `tests/test_context_budget_engine.py` (extender)

**Interfaces:**
- Consumes: `MemoryManager.build_context(...)`, `MemoryManager.fit_history(context, budget) -> dict` (Task 2); `estimate_tokens` (Task 1); `self._context_window`, `self._context_window_source`, `self._response_tokens` (Task 3)
- Produces: `context["_history_messages"]: list[{"role", "content"}]` para los patrones (ya lo leen `ReActPattern` y `GlyphPattern`); span `context_fit`.

- [ ] **Step 1: Write the failing tests** (agregar al final de `tests/test_context_budget_engine.py`)

```python
async def test_historial_llega_como_mensajes(tmp_path):
    agente = await _agente(
        tmp_path, _manifest(), turns=[_t("user", "me llamo Ana"), _t("assistant", "hola Ana")]
    )
    llamadas = _capturar(agente)
    await agente.run("¿cómo me llamo?", session_id="s1")
    assert llamadas[0][1:] == [
        {"role": "user", "content": "me llamo Ana"},
        {"role": "assistant", "content": "hola Ana"},
        {"role": "user", "content": "¿cómo me llamo?"},
    ]


async def test_template_legado_no_duplica_historial(tmp_path):
    system = "sos un agente\n{% for t in memory.conversation %}[{{ t.role }}] {{ t.content }}\n{% endfor %}"
    agente = await _agente(
        tmp_path,
        _manifest(system=system),
        turns=[_t("user", "me llamo Ana"), _t("assistant", "hola Ana")],
    )
    llamadas = _capturar(agente)
    await agente.run("¿cómo me llamo?", session_id="s1")
    assert len(llamadas[0]) == 2
    assert "[user] me llamo Ana" in llamadas[0][0]["content"]
    assert llamadas[0][1] == {"role": "user", "content": "¿cómo me llamo?"}


async def test_template_legado_avisa_al_cargar(tmp_path, caplog):
    import logging

    system = "{% for t in memory.conversation %}{{ t.content }}{% endfor %}"
    with caplog.at_level(logging.WARNING):
        await _agente(tmp_path, _manifest(system=system))
    avisos = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("mem-agent" in m and "rompe el caché de prompts" in m for m in avisos), avisos


async def test_presupuesto_recorta_y_conserva_lo_ultimo(tmp_path):
    model = {"primary": {"provider": "ollama", "model": "llama3", "context_window": 2000,
                         "max_tokens": 100}}
    turns = [_t("user" if i % 2 == 0 else "assistant", f"t{i:02d} " + "x" * 396) for i in range(40)]
    agente = await _agente(tmp_path, _manifest(model=model, max_turns=40), turns=turns)
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    historial = llamadas[0][1:-1]
    assert 0 < len(historial) < 40
    assert historial[-1]["content"].startswith("t39")


async def test_base_mayor_que_la_ventana_no_lanza(tmp_path):
    model = {"primary": {"provider": "ollama", "model": "llama3", "context_window": 50}}
    agente = await _agente(
        tmp_path, _manifest(system="x" * 4000, model=model), turns=[_t("user", "viejo")]
    )
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1:] == [{"role": "user", "content": "q"}]


async def test_historial_recortado_no_empieza_con_assistant(tmp_path):
    agente = await _agente(
        tmp_path,
        _manifest(),
        turns=[_t("assistant", "a0"), _t("user", "u1"), _t("assistant", "a1")],
    )
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1]["role"] == "user"
    assert llamadas[0][1]["content"] == "u1"


async def test_resumen_es_el_primer_mensaje(tmp_path):
    agente = await _agente(
        tmp_path, _manifest(strategy="summary"), turns=[_t("user", "u1"), _t("assistant", "a1")]
    )
    agente._memory._conversation.summary = "Ana pidió un turno"
    llamadas = _capturar(agente)
    await agente.run("q", session_id="s1")
    assert llamadas[0][1] == {
        "role": "user",
        "content": "[Resumen de la conversación anterior]\nAna pidió un turno",
    }


async def test_system_prompt_estable_entre_turnos(tmp_path):
    agente = await _agente(tmp_path, _manifest())
    llamadas = _capturar(agente)
    await agente.run("primero", session_id="s1")
    await agente.run("segundo", session_id="s1")
    assert llamadas[0][0] == llamadas[1][0]
    assert {"role": "user", "content": "primero"} in llamadas[1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context_budget_engine.py -v`
Expected: 7 de los 8 nuevos FAIL (el historial no llega como mensajes). `test_template_legado_avisa_al_cargar` ya pasa desde Task 3 — correcto, queda como guardia del cableado.

- [ ] **Step 3: Implement**

Helper de módulo en `engine.py` (junto a `_public_caller_context`):

```python
_SUMMARY_PREFIX = "[Resumen de la conversación anterior]"


def _history_messages(memory_context: dict) -> list[dict]:
    """El historial ya recortado, como mensajes para el patrón.

    Sin resumen adelante, se descartan los `assistant` iniciales: el recorte
    puede cortar en medio de un par, y hay proveedores que exigen que el primer
    mensaje sea del usuario.
    """
    turns = list(memory_context.get("conversation") or [])
    summary = memory_context.get("conversation_summary")
    messages = []
    if summary:
        messages.append({"role": "user", "content": f"{_SUMMARY_PREFIX}\n{summary}"})
    else:
        while turns and turns[0].role == "assistant":
            turns.pop(0)
    messages.extend({"role": t.role, "content": t.content} for t in turns)
    return messages
```

Método en `Agent`:

```python
    def _render_system(self, variables):
        prompt = self._prompt_engine.render(self._system_prompt, variables)
        if self._output_schema:
            # Ningún provider del repo soporta response_format/json_schema, así
            # que la forma se pide por prompt y se parsea de la respuesta.
            prompt += schema_prompt_block(self._output_schema)
        return prompt
```

En `Agent.run`, el bloque de memoria pasa a:

```python
            mem_span = tracing.start_span("memory_build")
            # Sin presupuesto acá: se recorta más abajo, cuando ya están medidos
            # el system prompt y las tools (`context_fit`).
            memory_context = await self._memory.build_context(session_id, query_text)
            tracing.finish_span(mem_span)
```

Y el bloque `prompt_render` hasta el cálculo de `tool_schemas` inclusive (desde `prompt_span = tracing.start_span("prompt_render")` hasta `tool_schemas = self._tools.get_tool_schemas(...)`) se reemplaza por:

```python
            tool_schemas = self._tools.get_tool_schemas(self._permissions.get("allowed_actions"))

            prompt_span = tracing.start_span("prompt_render")
            variables = {
                **(context or {}),
                "memory": memory_context,
                "knowledge": knowledge_context,
                "prefetch": prefetch_resultados,
            }
            # Base: el system prompt SIN historial. Es lo que viaja si el historial
            # va como mensajes, y así el prefijo es el mismo en cada turno (caché).
            rendered_prompt = self._render_system(
                {**variables, "memory": {**memory_context, "conversation": []}}
            )

            fit_span = tracing.start_span("context_fit")
            base_tokens = (
                estimate_tokens(rendered_prompt)
                + estimate_tokens(json.dumps(tool_schemas, default=str))
                + self._response_tokens
            )
            budget = max(0, int(self._context_window * 0.9) - base_tokens)
            if budget == 0:
                logger.warning(
                    "agent %s: el system prompt, las tools y la respuesta (%d tokens) no "
                    "dejan lugar para historial en una ventana de %d",
                    self.name,
                    base_tokens,
                    self._context_window,
                )
            stats = self._memory.fit_history(memory_context, budget)
            # Camino legado: el template mete `memory.conversation` en el system
            # prompt (manifiestos de OFFICIUM/Clarus). Se respeta y NO se mandan
            # mensajes, o el modelo vería el historial dos veces.
            history_in_template = "memory.conversation" in self._system_prompt
            if history_in_template:
                rendered_prompt = self._render_system(variables)
            else:
                memory_context["_history_messages"] = _history_messages(memory_context)
            for key, value in {
                "context.window": self._context_window,
                "context.window_source": self._context_window_source,
                "context.base_tokens": base_tokens,
                "history.budget": budget,
                "history.turns_kept": stats["turns_kept"],
                "history.turns_dropped": stats["turns_dropped"],
                "history.tokens": stats["tokens"],
                "history.delivery": "template" if history_in_template else "messages",
                "history.summary_used": stats["summary_used"],
            }.items():
                fit_span.set_attribute(key, value)
            tracing.finish_span(fit_span)
            tracing.finish_span(prompt_span)
```

Quitar la línea original `tool_schemas = self._tools.get_tool_schemas(...)` que quedaba después del render (ya se calculó arriba). El resto de `run` (incluido `{**memory_context, "_caller_context": ...}` al llamar al patrón) no cambia: `_history_messages` viaja dentro de `memory_context`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_context_budget_engine.py -v`
Expected: 12 passed.

Run: `uv run pytest -q`
Expected: toda la suite verde. Si falla un test que fijaba el system prompt con historial adentro o que esperaba `messages` sin historial, leerlo antes de tocarlo: el cambio de comportamiento es intencional sólo para agentes con `memory.conversational`.

- [ ] **Step 5: CHANGELOG, lint, format, commit**

CHANGELOG, bajo `## [Unreleased]`:

```markdown
### Fixed
- **El historial llega al modelo como mensajes, con presupuesto real.** El presupuesto es la
  ventana del modelo menos el system prompt, las tools y la respuesta (antes 4096 fijos). Los
  agentes con `memory.conversational` cuyo system prompt no usa `memory.conversation`
  **empiezan a recordar** la conversación (antes no la recibían), y el system prompt queda
  igual entre turnos, así que el caché de prompts puede actuar. Los templates que meten
  `memory.conversation` en el system prompt siguen andando igual y emiten un warning al
  cargar.

### Changed
- Sólo los patrones `react` y `glyph` consumen el historial como mensajes; los demás siguen
  como antes.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py tests/test_context_budget_engine.py CHANGELOG.md
git commit -m "fix(runtime): historial con presupuesto real y entregado como mensajes"
```

---

### Task 5: Guía de configuración y verificación final

**Files:**
- Modify: `docs/CONFIGURATION_GUIDE.md` (sección de memoria conversacional, cerca de la tabla de estrategias ~línea 310)
- Verify: `CHANGELOG.md` ya tiene las entradas de Tasks 1-4 bajo `## [Unreleased]`, sin duplicar encabezados `### Fixed`/`### Changed` (fusionarlos si quedaron repetidos).

- [ ] **Step 1: Guía de configuración**

En `docs/CONFIGURATION_GUIDE.md`, debajo de la tabla de estrategias, agregar:

```markdown
**Presupuesto del historial.** El runtime toma la ventana del modelo — `context_window` en el
candidato, o `parameters.num_ctx` en Ollama, o lo que sepa litellm si está instalado, o
32000 — y le resta el system prompt, los schemas de las tools y `max_tokens` de la
respuesta (con 10% de margen). El historial entra hasta ese tope, de lo más nuevo a lo más
viejo. Con varios candidatos se usa la ventana más chica.

```yaml
model:
  primary:
    provider: ollama
    model: llama3
    context_window: 8192
```

El historial viaja como mensajes. No lo metas en el system prompt con
`{% for t in memory.conversation %}`: funciona, pero cambia el prompt en cada turno y anula
el caché de prompts.
```

- [ ] **Step 2: Verificación completa**

```bash
uv run pytest -q
uv run ruff check astromesh/ tests/
uv run ruff format --check astromesh/ tests/
```

Expected: todo verde, `ruff format --check` sin archivos a reformatear.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md docs/CONFIGURATION_GUIDE.md
git commit -m "docs: guía de configuración — presupuesto real del historial conversacional"
```

- [ ] **Step 4: Seguimiento fuera de este repo** — anotar (no implementar) que el schema de Cortex, mantenido a mano, necesita `context_window` en el bloque del candidato.
