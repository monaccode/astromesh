# Tope por observación de tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el resultado de una tool entre al mensaje del modelo con un tope de tokens que respeta su estructura (lista/dict/texto), serializado como JSON en lugar del repr de Python, configurable por tool y por agente.

**Architecture:** Una unidad pura `orchestration/observaciones.py` (`presentar`) hace la serialización y el recorte. `ciclo_de_tools` la aplica a cada observación antes de agregarla a `messages`, con un presupuesto que el engine arma al cargar el agente y pasa a los patrones por `context["_presupuesto_tools"]`. Glyph no pasa por ahí y sigue recibiendo datos completos.

**Tech Stack:** Python 3.12, pytest (asyncio auto), uv.

**Spec:** `docs/superpowers/specs/2026-10-06-tool-result-budget-design.md`

## Global Constraints

- Trabajar SÓLO en el worktree `/Users/fulfaro/monaccode/astromesh-tool-budget` (rama `feat/tool-result-budget`, desde `origin/develop` 0.65.0). NO tocar `/Users/fulfaro/monaccode/astromesh` (su `develop` local tiene trabajo de otra sesión). Nunca `git stash`. No pushear.
- `DEFAULT_MAX_TOOL_RESULT_TOKENS = 8000`.
- Serialización: `str` → tal cual; otro → `json.dumps(obs, ensure_ascii=False, separators=(",", ":"), default=str)`.
- Aviso de lista: `{"_omitidos": N, "_nota": "resultado recortado: hay N elementos más; pedí un filtro más específico"}` como último elemento.
- Marcador de texto: `"\n[resultado recortado: X de Y tokens]"` (X = tokens conservados aprox., Y = tokens originales).
- Medición en tokens con `astromesh.core.tokens.estimate_tokens`.
- `presentar` nunca lanza.
- Claves YAML: `tools[].max_result_tokens` (int > 0), `orchestration.max_tool_result_tokens` (int > 0). Inválidas → warning al cargar y default.
- Canal a los patrones: `memory_context["_presupuesto_tools"] = {"default": int, "por_tool": {nombre_registrado: int}}`.
- Traza: span `tool.call` + `tool.result_tokens`; step en `orch_step` + `truncated: True`, `omitted: N` cuando hubo recorte.
- Comandos: `uv run pytest -q <rutas>`, `uv run ruff check astromesh/ tests/`, `uv run ruff format --check astromesh/ tests/` (los dos ruff antes de cada commit). Line length 100.
- Cada commit `feat:`/`fix:` lleva su entrada en `CHANGELOG.md` bajo `## [Unreleased]` en el mismo commit (crear la sección si no existe, arriba de `## [0.65.0]`), sin duplicar encabezados.
- Commits en español; terminar con una línea en blanco y `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- En tests que comparan tokens exactos, parchear `astromesh.core.tokens._litellm` a `lambda: None` (litellm está instalado en dev).

## Review Focus

1. **Un único elemento de lista más grande que todo el presupuesto**: no se devuelve `[aviso]` sin datos sin decirlo; cae al recorte de texto sobre el JSON (el modelo ve al menos la cabeza del primer elemento) — test en Task 1.
2. **Presupuesto muy chico** (p. ej. 1–10 tokens): no explota ni devuelve string vacío; devuelve algo con el marcador — test en Task 1.
3. **Observación `None` o vacía**: se presenta como `"null"`/`""` sin recorte — test en Task 1.
4. **Resultado de sub-agente** `{"answer": "...", "data": [...]}` con `data` enorme: recorta `data` y conserva `answer` — test en Task 1.
5. **Tool de integración** que registra varias acciones desde una sola definición: `max_result_tokens` aplica a todas (`<slug>_<acción>`) — test en Task 3.

---

### Task 1: `presentar` — serializar y recortar respetando la estructura

**Files:**
- Create: `astromesh/orchestration/observaciones.py`
- Test: `tests/test_observaciones.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: `DEFAULT_MAX_TOOL_RESULT_TOKENS: int = 8000`; `presentar(observacion, max_tokens: int) -> tuple[str, dict]` con dict `{"tokens": int, "truncated": bool, "omitted": int}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_observaciones.py
import json

import pytest

from astromesh.core import tokens
from astromesh.orchestration.observaciones import DEFAULT_MAX_TOOL_RESULT_TOKENS, presentar


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def test_default_es_8000():
    assert DEFAULT_MAX_TOOL_RESULT_TOKENS == 8000


def test_string_que_entra_va_tal_cual():
    assert presentar("hola", 100) == ("hola", {"tokens": 1, "truncated": False, "omitted": 0})


def test_dict_se_serializa_como_json_no_repr():
    texto, meta = presentar({"ok": True, "nada": None, "ñ": "año"}, 100)
    assert texto == '{"ok":true,"nada":null,"ñ":"año"}'
    assert meta["truncated"] is False


def test_none_y_vacio():
    assert presentar(None, 100)[0] == "null"
    assert presentar("", 100)[0] == ""


def test_lista_que_no_entra_conserva_el_principio_y_avisa():
    filas = [{"id": i, "nombre": "x" * 36} for i in range(200)]  # ~13 tokens c/u
    texto, meta = presentar(filas, 300)
    datos = json.loads(texto)  # JSON válido
    assert datos[0] == {"id": 0, "nombre": "x" * 36}
    aviso = datos[-1]
    assert set(aviso) == {"_omitidos", "_nota"}
    assert aviso["_omitidos"] == 200 - (len(datos) - 1)
    assert meta == {"tokens": meta["tokens"], "truncated": True, "omitted": aviso["_omitidos"]}
    assert meta["tokens"] > 300
    assert tokens.estimate_tokens(texto) <= 300


def test_dict_con_lista_grande_recorta_esa_lista_y_deja_el_resto():
    obs = {"total": 500, "data": [{"id": i, "v": "y" * 40} for i in range(500)], "ok": True}
    texto, meta = presentar(obs, 400)
    datos = json.loads(texto)
    assert datos["total"] == 500 and datos["ok"] is True
    assert datos["data"][-1]["_omitidos"] == meta["omitted"] > 0
    assert tokens.estimate_tokens(texto) <= 400


def test_sub_agente_conserva_answer_y_recorta_data():
    obs = {"answer": "listo", "data": ["z" * 100 for _ in range(300)]}
    texto, _ = presentar(obs, 500)
    datos = json.loads(texto)
    assert datos["answer"] == "listo"
    assert "_omitidos" in datos["data"][-1]


def test_texto_que_no_entra_lleva_marcador():
    texto, meta = presentar("a" * 4000, 100)  # 1000 tokens
    assert texto.endswith("[resultado recortado: 100 de 1000 tokens]")
    assert meta == {"tokens": 1000, "truncated": True, "omitted": 0}


def test_dict_sin_listas_que_no_entra_cae_a_texto():
    texto, meta = presentar({"blob": "b" * 4000}, 100)
    assert "[resultado recortado:" in texto
    assert meta["truncated"] is True and meta["omitted"] == 0


def test_un_elemento_mas_grande_que_el_presupuesto_cae_a_texto():
    texto, meta = presentar([{"blob": "c" * 4000}], 100)
    assert "[resultado recortado:" in texto
    assert texto.startswith('[{"blob":"ccc')


def test_presupuesto_minimo_no_explota():
    texto, meta = presentar("d" * 400, 1)
    assert "[resultado recortado:" in texto
    assert meta["truncated"] is True


def test_no_serializable_usa_default_str():
    class Raro:
        def __str__(self):
            return "raro"

    assert presentar({"x": Raro()}, 100)[0] == '{"x":"raro"}'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_observaciones.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'astromesh.orchestration.observaciones'`.

- [ ] **Step 3: Implement**

```python
# astromesh/orchestration/observaciones.py
"""Cómo entra el resultado de una tool al mensaje del modelo.

Un resultado sin tope se paga entero la primera vez y ocupa ventana; el
reenvío en las vueltas siguientes lo sirve el caché de prefijo, así que el
tope va en el momento en que la observación ENTRA, nunca reescribiendo las
anteriores (rompería el prefijo). Glyph no pasa por acá: sus programas usan
los resultados como datos, y recortarlos cambiaría lo que calculan.
"""

import json
import logging
import math

from astromesh.core.tokens import estimate_tokens

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_RESULT_TOKENS = 8000


def _serializar(obs) -> str:
    if isinstance(obs, str):
        return obs
    return json.dumps(obs, ensure_ascii=False, separators=(",", ":"), default=str)


def _aviso(n: int) -> dict:
    return {
        "_omitidos": n,
        "_nota": f"resultado recortado: hay {n} elementos más; pedí un filtro más específico",
    }


def _recortar_lista(lista: list, armar, max_tokens: int):
    """El prefijo más largo de `lista` tal que `armar(prefijo + [aviso])` entra.

    `armar` envuelve la lista recortada en el objeto completo (la lista sola, o
    el dict con esa clave reemplazada). Devuelve (texto, omitidos) o None si ni
    un elemento entra.
    """
    lo, hi, mejor = 1, len(lista) - 1, None
    while lo <= hi:
        k = (lo + hi) // 2
        texto = _serializar(armar(lista[:k] + [_aviso(len(lista) - k)]))
        if estimate_tokens(texto) <= max_tokens:
            mejor, lo = (texto, len(lista) - k), k + 1
        else:
            hi = k - 1
    return mejor


def _recorte_de_texto(texto: str, total: int, max_tokens: int) -> str:
    marcador = f"\n[resultado recortado: {max_tokens} de {total} tokens]"
    # ponytail: corte por caracteres con la proporción de tokens; el marcador
    # puede pasar el tope por unos pocos tokens.
    largo = max(0, math.floor(len(texto) * max_tokens / max(total, 1)) - len(marcador))
    return texto[:largo] + marcador


def presentar(observacion, max_tokens: int) -> tuple[str, dict]:
    try:
        texto = _serializar(observacion)
        total = estimate_tokens(texto)
        if total <= max_tokens:
            return texto, {"tokens": total, "truncated": False, "omitted": 0}
        if isinstance(observacion, list) and len(observacion) > 1:
            r = _recortar_lista(observacion, lambda xs: xs, max_tokens)
            if r:
                return r[0], {"tokens": total, "truncated": True, "omitted": r[1]}
        if isinstance(observacion, dict):
            listas = [
                (estimate_tokens(_serializar(v)), k)
                for k, v in observacion.items()
                if isinstance(v, list) and len(v) > 1
            ]
            if listas:
                _, clave = max(listas)
                r = _recortar_lista(
                    observacion[clave], lambda xs: {**observacion, clave: xs}, max_tokens
                )
                if r:
                    return r[0], {"tokens": total, "truncated": True, "omitted": r[1]}
        return _recorte_de_texto(texto, total, max_tokens), {
            "tokens": total,
            "truncated": True,
            "omitted": 0,
        }
    except Exception:  # noqa: BLE001 — presentar nunca hace fallar la corrida
        logger.debug("presentar falló; recorte de texto plano", exc_info=True)
        crudo = str(observacion)
        total = estimate_tokens(crudo)
        if total <= max_tokens:
            return crudo, {"tokens": total, "truncated": False, "omitted": 0}
        return _recorte_de_texto(crudo, total, max_tokens), {
            "tokens": total,
            "truncated": True,
            "omitted": 0,
        }
```

(Si ruff marca `# noqa: BLE001` como innecesario —RUF100—, quitarlo. Si el test de `test_lista_que_no_entra…` falla por uno o dos tokens en `estimate_tokens(texto) <= 300`, el bug está en la búsqueda, no en el test: la búsqueda binaria garantiza que el texto devuelto entra.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_observaciones.py -q`
Expected: PASS.

- [ ] **Step 5: CHANGELOG, lint, commit**

CHANGELOG, `## [Unreleased]` → `### Added (Backend)`:

```markdown
- `astromesh/orchestration/observaciones.py`: `presentar` serializa el resultado de una tool como
  JSON y lo recorta a un presupuesto de tokens respetando su estructura (prefijo de una lista con
  aviso de omitidos, la lista más grande de un dict, o la cabeza del texto con marcador).
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/orchestration/observaciones.py tests/test_observaciones.py CHANGELOG.md
git commit -m "feat(orchestration): presentar — el resultado de una tool como JSON y con tope de tokens"
```

---

### Task 2: `ciclo_de_tools` aplica el tope; los patrones pasan el presupuesto

**Files:**
- Modify: `astromesh/orchestration/patterns.py` (`AgentStep`, `ciclo_de_tools` ~58-127, llamadas en ReAct ~143, plan_and_execute ~197, pipeline ~263, fan_out ~334)
- Modify: `astromesh/orchestration/supervisor.py` (~24)
- Test: `tests/test_tool_result_budget.py`
- Modify: tests existentes que fijaban el repr de Python en la observación (buscar con `grep -rn "{'" tests/test_patterns*.py tests/test_*pattern*.py`)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `presentar`, `DEFAULT_MAX_TOOL_RESULT_TOKENS` (Task 1).
- Produces: `AgentStep.recorte: dict | None = None`; `ciclo_de_tools(..., permitidas=None, presupuesto=None)` con `presupuesto: {"default": int, "por_tool": dict[str, int]} | None`; los patrones leen `context.get("_presupuesto_tools")` (guard `isinstance(context, dict)`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tool_result_budget.py
import json

import pytest

from astromesh.core import tokens
from astromesh.orchestration.patterns import (
    AgentStep,
    ReActPattern,
    ciclo_de_tools,
)


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


class Resp:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = {}


def modelo_que_llama(nombre):
    """Primera vuelta: pide `nombre`; segunda: contesta."""
    llamadas = []

    async def model_fn(messages, tools, role=None):
        llamadas.append(list(messages))
        if len(llamadas) == 1:
            return Resp(tool_calls=[{"id": "t1", "name": nombre, "arguments": {}}])
        return Resp(content="listo")

    return model_fn, llamadas


GRANDE = [{"id": i, "v": "x" * 40} for i in range(2000)]


async def _correr(presupuesto, nombre="buscar", resultado=GRANDE):
    model_fn, llamadas = modelo_que_llama(nombre)

    async def tool_fn(name, args):
        return resultado

    r = await ciclo_de_tools(
        [{"role": "user", "content": "q"}], model_fn, tool_fn, [], 5, "reasoner",
        presupuesto=presupuesto,
    )
    tool_msg = next(m for m in llamadas[1] if m["role"] == "tool")
    return r, tool_msg


async def test_sin_presupuesto_usa_el_default():
    r, msg = await _correr(None)
    assert tokens.estimate_tokens(msg["content"]) <= 8000
    assert json.loads(msg["content"])[-1]["_omitidos"] > 0


async def test_por_tool_gana_sobre_default():
    _, msg = await _correr({"default": 8000, "por_tool": {"buscar": 200}})
    assert tokens.estimate_tokens(msg["content"]) <= 200


async def test_default_del_agente_si_la_tool_no_tiene_propio():
    _, msg = await _correr({"default": 300, "por_tool": {"otra": 50}})
    assert 50 < tokens.estimate_tokens(msg["content"]) <= 300


async def test_dict_llega_como_json():
    _, msg = await _correr(None, resultado={"ok": True, "v": None})
    assert msg["content"] == '{"ok":true,"v":null}'


async def test_el_step_lleva_el_recorte_solo_si_hubo():
    r, _ = await _correr({"default": 200, "por_tool": {}})
    paso = next(s for s in r["steps"] if s.action == "buscar")
    assert paso.recorte["truncated"] is True and paso.recorte["omitted"] > 0
    r2, _ = await _correr(None, resultado="corto")
    paso2 = next(s for s in r2["steps"] if s.action == "buscar")
    assert paso2.recorte is None


async def test_react_pasa_el_presupuesto_del_context():
    model_fn, llamadas = modelo_que_llama("buscar")

    async def tool_fn(name, args):
        return GRANDE

    await ReActPattern().execute(
        query="q",
        context={"_presupuesto_tools": {"default": 150, "por_tool": {}}},
        model_fn=model_fn,
        tool_fn=tool_fn,
        tools=[],
    )
    tool_msg = next(m for m in llamadas[1] if m["role"] == "tool")
    assert tokens.estimate_tokens(tool_msg["content"]) <= 150
```

Agregar además un test por patrón (`PlanAndExecutePattern`, `PipelinePattern`, `ParallelFanOutPattern`, `SupervisorPattern`) con la misma forma: un `model_fn` guionado que haga que el patrón llame UNA tool que devuelve `GRANDE`, `context={"_presupuesto_tools": {"default": 150, "por_tool": {}}}`, y aseverar que el mensaje `role: tool` que vio el modelo tiene `estimate_tokens <= 150`. Leer los tests existentes de cada patrón (`grep -rln "PlanAndExecutePattern\|PipelinePattern\|ParallelFanOutPattern\|SupervisorPattern" tests/`) y copiar su forma de guionar el modelo (cada patrón tiene su protocolo de planificación/pasos); importar las clases desde donde las importan esos tests.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_result_budget.py -q`
Expected: FAIL — `ciclo_de_tools() got an unexpected keyword argument 'presupuesto'`.

- [ ] **Step 3: Implement**

En `patterns.py`:

```python
from astromesh.orchestration.observaciones import DEFAULT_MAX_TOOL_RESULT_TOKENS, presentar
```

`AgentStep` gana `recorte: dict | None = None` (último campo).

En `ciclo_de_tools`, firma `async def ciclo_de_tools(messages, model_fn, tool_fn, tools, max_iterations, role, permitidas=None, presupuesto=None):` y, antes del loop:

```python
    por_tool = (presupuesto or {}).get("por_tool") or {}
    default = (presupuesto or {}).get("default") or DEFAULT_MAX_TOOL_RESULT_TOKENS
```

Reemplazar el bloque que arma el `AgentStep` y el mensaje `tool` por:

```python
            texto, meta = presentar(observation, por_tool.get(tc["name"], default))
            steps.append(
                AgentStep(
                    thought=response.content,
                    action=tc["name"],
                    action_input=tc["arguments"],
                    observation=texto,
                    recorte=meta if meta["truncated"] else None,
                )
            )
            messages.append({"role": "tool", "content": texto, "tool_call_id": tc["id"]})
```

En cada llamada a `ciclo_de_tools` (ReAct, plan_and_execute, pipeline, fan_out en `patterns.py`, y supervisor en `supervisor.py`) agregar `presupuesto=presupuesto_de(context)`, con un helper en `patterns.py`:

```python
def presupuesto_de(context) -> dict | None:
    """El presupuesto de observaciones que armó el engine (`_presupuesto_tools`)."""
    return context.get("_presupuesto_tools") if isinstance(context, dict) else None
```

(importarlo en `supervisor.py` desde `patterns`). Si alguna llamada está dentro de una función interna que no recibe `context`, pasar el valor ya calculado al principio de `execute`.

Actualizar los tests existentes que fijaban el repr de Python en `observation`/mensaje `tool` (ahora JSON compacto); no debilitar otros asserts.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_tool_result_budget.py tests/test_observaciones.py -q` y después `uv run pytest -q` (suite entera).
Expected: PASS.

- [ ] **Step 5: CHANGELOG, lint, commit**

CHANGELOG, `## [Unreleased]`:

```markdown
### Changed
- **El resultado de una tool entra al modelo con tope y como JSON.** `ciclo_de_tools` (ReAct,
  plan_and_execute, pipeline, fan_out, supervisor) pasa cada observación por `presentar`: un
  dict/lista llega como JSON compacto en lugar del repr de Python, y lo que supera el presupuesto se
  recorta respetando la estructura (default 8000 tokens). Glyph no cambia: sus programas reciben los
  datos completos.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/orchestration/patterns.py astromesh/orchestration/supervisor.py tests/ CHANGELOG.md
git commit -m "feat(orchestration): ciclo_de_tools recorta cada observación a su presupuesto"
```

---

### Task 3: Engine — presupuesto desde el YAML, canal a los patrones, traza y schema

**Files:**
- Modify: `astromesh/runtime/engine.py`: `_CLAVES_COMUNES` (~193), loop `for tool_def in spec.get("tools", [])` en `_build_agent` (~902), `Agent.__init__`, `Agent.run` (junto a `memory_context["_turn_context"] = …` ~1681), span `tool.call` en `tool_fn` (~1857-1882), volcado de steps (~1917-1931)
- Modify: `vscode-extension/schemas/agent.schema.json` (`properties.spec.properties.tools.items.properties` y `properties.spec.properties.orchestration.properties`)
- Test: `tests/test_tool_result_budget_engine.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `DEFAULT_MAX_TOOL_RESULT_TOKENS` (Task 1); `_presupuesto_tools` leído por los patrones (Task 2); `AgentStep.recorte` (Task 2).
- Produces: `Agent._presupuesto_tools: dict`; `memory_context["_presupuesto_tools"]`.

- [ ] **Step 1: Write the failing tests**

Reusar la forma de `tests/test_context_budget_engine.py` (un `AgentRuntime` desde YAML en `tmp_path`, `_capturar` el router `default`). Tests:

```python
# tests/test_tool_result_budget_engine.py
import logging

import pytest
import yaml

from astromesh.core import tokens
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


GRANDE = [{"id": i, "v": "x" * 40} for i in range(2000)]


async def grande(**kwargs):
    return GRANDE


def _manifest(tools, orchestration=None):
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": "tb-agent", "version": "0.1.0"},
        "spec": {
            "identity": {"description": "demo"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
            "orchestration": {"pattern": "react", **(orchestration or {})},
            "tools": tools,
        },
    }


async def _agente(tmp_path, manifest):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    (d / "agents" / "tb-agent.agent.yaml").write_text(yaml.safe_dump(manifest))
    rt = AgentRuntime(config_dir=str(d))
    await rt.bootstrap()
    assert "tb-agent" in rt._agents, rt._agent_errors
    return rt._agents["tb-agent"]


def _guion(agente, tool_name):
    vistos = []

    async def route(messages, requirements=None, **kw):
        vistos.append(list(messages))
        if len(vistos) == 1:
            return CompletionResponse(
                content="", model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0,
                tool_calls=[{"id": "t1", "name": tool_name, "arguments": {}}],
            )
        return CompletionResponse(
            content="ok", model="m", provider="p", usage={}, latency_ms=1.0, cost=0.0
        )

    agente._routers["default"].route = route
    return vistos
```

Casos (escribir cada uno; registrar la tool del test con `agente._tools.register_internal(name=..., handler=grande, description="d", parameters={"type": "object", "properties": {}})` DESPUÉS de cargar — o, si el manifiesto necesita declararla para que `max_result_tokens` se mapee, usar un `type: builtin` existente del catálogo que el runtime cargue sin red y reemplazar su handler en `agente._tools._tools[nombre]`; leer `tests/test_engine_builtin.py` para elegir uno):

1. `tools[].max_result_tokens: 150` en una tool → el mensaje `tool` que ve el modelo tiene `estimate_tokens <= 150`.
2. `orchestration.max_tool_result_tokens: 300` sin override → `<= 300`.
3. Sin nada → `<= 8000` y con `_omitidos`.
4. Valor inválido (`0`, `-5`, `"mucho"`) en tool y en orchestration → warning al cargar que nombra agente, tool (si aplica) y valor (`caplog.at_level(logging.WARNING)` alrededor de `bootstrap`), y se usa el default.
5. `max_result_tokens` no dispara el aviso de «clave ignorada» para `builtin`, `agent`, `client`, `integration`, `api`, `mcp` (unit test sobre `claves_ignoradas({"type": t, "name": "x", "max_result_tokens": 10})` → `[]` para cada `t`).
6. Integración con varias acciones (`type: integration`, una del catálogo que cargue sin red; mirar `tests/test_caller_context_engine.py`, que arma un catálogo en `tmp_path`) con `max_result_tokens: 120` → `agente._presupuesto_tools["por_tool"]` tiene 120 para CADA nombre registrado `<slug>_<acción>`.
7. Traza: la respuesta de `agente.run(...)` trae en `result["trace"]["spans"]` un `tool.call` con `attributes["tool.result_tokens"] > 8000` y, en los eventos `orch_step` del span de orquestación, un step con `truncated: True` y `omitted > 0`.
8. Glyph recibe los datos completos: `GlyphPattern(program="v = buscar(q=\"a\")\nreturn v\n", narrate=False)` ejecutado con un `tool_fn` que devuelve `GRANDE` y `context={"_presupuesto_tools": {"default": 50, "por_tool": {}}}` → el resultado contiene los 2000 elementos (mirar `tests/test_glyph_pattern.py` para el catálogo `TOOLS` y cómo leer el resultado de un programa fijo con `narrate=False`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tool_result_budget_engine.py -q`
Expected: FAIL (sin mapa ni canal; `max_result_tokens` dispara clave ignorada).

- [ ] **Step 3: Implement**

- `_CLAVES_COMUNES = frozenset({"type", "name", "confirm", "max_result_tokens"})` con un comentario: vale para todos los tipos (`orchestration/observaciones.py`).
- Helper de módulo:

```python
def _tokens_validos(valor) -> int | None:
    """Un presupuesto de tokens del YAML: entero > 0 (no bool), o None."""
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        return None
    return valor
```

- En `_build_agent`, alrededor del loop de tools, asignar el presupuesto de cada definición a los nombres que registró, sin reindentar el cuerpo del loop:

```python
        por_tool: dict[str, int] = {}
        pendiente: tuple[dict, set] | None = None

        def _cerrar(p):
            if p is None or "max_result_tokens" not in p[0]:
                return
            valor = _tokens_validos(p[0]["max_result_tokens"])
            if valor is None:
                logger.warning(
                    "agent %r: tool %r declara max_result_tokens=%r, que no es un entero > 0; "
                    "se usa el presupuesto del agente.",
                    metadata["name"], p[0].get("name"), p[0]["max_result_tokens"],
                )
                return
            for nombre in set(tools._tools) - p[1]:
                por_tool[nombre] = valor

        for tool_def in spec.get("tools", []):
            _cerrar(pendiente)
            pendiente = (tool_def, set(tools._tools))
            ... (cuerpo actual sin cambios)
        _cerrar(pendiente)
```

  (Ojo: el cuerpo tiene `continue`s; por eso el cierre va al principio de la iteración siguiente y después del loop, no al final del cuerpo.)
- Default del agente: `orq = spec.get("orchestration") or {}`; si trae `max_tool_result_tokens`, `_tokens_validos`; inválido → warning análogo nombrando agente y valor. `presupuesto_tools = {"default": valor or DEFAULT_MAX_TOOL_RESULT_TOKENS, "por_tool": por_tool}`; pasarlo a `Agent(...)` como `presupuesto_tools=` (parámetro nuevo con default `None` → `{"default": DEFAULT_MAX_TOOL_RESULT_TOKENS, "por_tool": {}}`), guardado en `self._presupuesto_tools`.
- En `Agent.run`, junto a donde se escribe `memory_context["_turn_context"]` (y en la rama donde no hay contexto de turno también): `memory_context["_presupuesto_tools"] = self._presupuesto_tools`, después de todos los renders.
- En `tool_fn`, span `tool.call`: después de obtener `observation`, `tool_span.set_attribute("tool.result_tokens", estimate_tokens(observation if isinstance(observation, str) else json.dumps(observation, ensure_ascii=False, default=str)))` — envolverlo en try/except que lo ignore (la métrica no puede romper la corrida).
- Volcado de steps (`step_data`): `if getattr(step, "recorte", None): step_data["truncated"] = True; step_data["omitted"] = step.recorte.get("omitted", 0)`.
- Schema: en `properties.spec.properties.tools.items.properties` agregar `"max_result_tokens": {"type": "integer", "minimum": 1, "description": "Tope de tokens del resultado de esta tool al entrar al mensaje del modelo (orchestration/observaciones.py). Sin él rige orchestration.max_tool_result_tokens o 8000."}`; en `properties.spec.properties.orchestration.properties`: `"max_tool_result_tokens": {"type": "integer", "minimum": 1, "description": "Tope por defecto de tokens del resultado de una tool para este agente (default 8000)."}`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_tool_result_budget_engine.py tests/test_tool_result_budget.py tests/test_agent_schema.py tests/test_claves_ignoradas.py -q` y después `uv run pytest -q`.
Expected: PASS.

- [ ] **Step 5: CHANGELOG, lint, commit**

CHANGELOG, `## [Unreleased]`:

```markdown
### Added (Backend)
- `tools[].max_result_tokens` y `orchestration.max_tool_result_tokens`: el tope de tokens del
  resultado de una tool, por tool y por agente (default 8000). En una integración, api o mcp, el
  valor aplica a todas las tools que esa definición registra. Un valor inválido avisa al cargar y
  usa el default.
- Traza: `tool.result_tokens` en el span `tool.call`; los steps recortados llevan `truncated` y
  `omitted`.
```

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/runtime/engine.py vscode-extension/schemas/agent.schema.json tests/test_tool_result_budget_engine.py CHANGELOG.md
git commit -m "feat(runtime): presupuesto de resultados de tools desde el YAML, a los patrones y a la traza"
```

---

### Task 4: Documentación

**Files:**
- Modify: `docs-site/src/content/docs/configuration/agent-yaml.md`, `docs-site/src/content/docs/advanced/prompt-caching.md`, `docs-site/src/content/docs/advanced/observability.md`

- [ ] **Step 1: Docs**

- `agent-yaml.md`: en la sección de tools, `max_result_tokens` (qué hace, default, cómo recorta: lista/dict/texto, JSON en lugar del repr, aplica a todas las tools de una integración/api/mcp); en orchestration, `max_tool_result_tokens`. Mencionar que glyph recibe datos completos.
- `prompt-caching.md`: una línea en la sección de presupuesto: los resultados de tools tienen su propio tope al entrar (no se reescriben después, para no romper el prefijo).
- `observability.md`: `tool.result_tokens` en `tool.call`, y `truncated`/`omitted` en los eventos `orch_step`.
- Links internos con el prefijo `/astromesh/` (como el resto del sitio).

- [ ] **Step 2: Build**

Run: `cd docs-site && npm run build`
Expected: build OK, sin links rotos.

- [ ] **Step 3: Commit**

```bash
git add docs-site/src/content/docs
git commit -m "docs(site): tope de resultados de tools en agent-yaml, caché y observabilidad"
```
