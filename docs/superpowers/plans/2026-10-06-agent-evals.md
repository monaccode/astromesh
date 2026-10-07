# Evals de agentes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un formato `kind: Eval` y un runner in-process, `astromesh-eval <config_dir>`, que corre casos contra agentes con tools stubeadas y memoria aislada. Reporta calidad, tokens y costo, y sale con error bajo umbral.

**Architecture:** Módulo nuevo `astromesh/evals/`, que `api.main` nunca importa:
- `formato.py`: cargador y validación.
- `asserts.py`: asserts puros.
- `memoria.py`: backend conversacional en memoria.
- `fixtures.py`: wrapper de `ToolRegistry.execute`, con un `ContextVar` por caso.
- `juez.py`: juez LLM.
- `runner.py`: corre un eval contra un `AgentRuntime` ya arrancado.
- `__main__.py`: CLI.

**Tech Stack:** Python 3.12, sólo stdlib más lo que el core ya tiene (`pyyaml`). pytest con `asyncio_mode = "auto"`.

**Spec:** `docs/superpowers/specs/2026-10-06-agent-evals-design.md`

## Global Constraints

- **Sin dependencias nuevas.** `jsonschema` es dependencia de dev, así que el código de `astromesh/evals/` no lo importa; sólo lo usan los tests.
- **`astromesh/api/main.py` no importa `astromesh.evals`.** La imagen de astromesh-os arranca sin extras.
- **Se tocan los tests del motor, no el motor.** No cambia el comportamiento de `astromesh/runtime/engine.py`, `astromesh/core/tools.py` ni `astromesh/core/memory.py`. El runner los adapta desde afuera: asigna `agent._memory._conversation` y reemplaza `registry.execute` en la instancia.
- **Ruff y estilo.** Largo de línea 100. Antes de cada commit, corré `uv run ruff check astromesh/ tests/` y `uv run ruff format --check astromesh/ tests/`; CI corre los dos.
- **Idioma.** Los identificadores y mensajes nuevos van en español, como `observaciones.py`. Commits convencionales.
- **Changelog.** Va bajo `## [Unreleased]` → `### Added` en el mismo commit `feat:` (Task 6).
- **Mensajes de error exactos:**
  - tool bloqueada: `tool sin fixture en el eval: <nombre>`;
  - el `session_id` de un caso es `eval-<run_id>-<case_id>`.
- **Exit codes.** `0` si todos los evals cumplen, `1` si alguno no, `2` por error de carga (y entonces no corre ningún caso).
- **Default del juez.** `pass_score` vale `0.7` si no se declara.

## Review Focus

1. **Contexto mutado entre turnos.** El `context` de un caso se pasa en cada turno. Si el runtime lo muta, el turno 2 vería basura, así que se pasa una copia profunda por turno. Lo testea Task 5 (`test_context_se_copia_por_turno`).
2. **Una tool de sub-agente stubeada por nombre.** El wrapper se instala en el registry de **todos** los agentes, y una segunda instalación no envuelve dos veces. Lo testea Task 3 (`test_instalar_es_idempotente`).
3. **Fixture mutada por el agente.** Se devuelve una copia profunda, y el caso siguiente con la misma fixture ve el original. Lo testea Task 3 (`test_fixture_se_devuelve_como_copia`).
4. **El juez devuelve JSON envuelto en fences.** Un `` ```json … ``` `` es lo más común en modelos chat. Se acepta quitando el fence, y lo testea Task 4 (`test_acepta_json_en_fence`).
5. **Regex inválida en un assert.** Tiene que ser error de carga, no una excepción en medio del eval. Lo testea Task 1 (`test_regex_invalida_es_error_de_carga`).

---

### Task 1: Formato `kind: Eval` — cargador y schema

**Files:**
- Create: `astromesh/evals/__init__.py`
- Create: `astromesh/evals/formato.py`
- Create: `vscode-extension/schemas/eval.schema.json`
- Create: `tests/evals/__init__.py` (vacío), `tests/evals/test_formato.py`

**Interfaces:**
- Produces:
  - `EvalError(ValueError)`.
  - `ASSERTS: frozenset[str]`.
  - `Caso(id: str, turns: list[str], context: dict, tools: dict, expect: list[dict], rubric: str | None)`.
  - `Eval(name: str, agent: str, pass_rate: float, casos: list[Caso], max_avg_tokens: int | None, tools_default: str, judge_model: dict | None, judge_pass_score: float, path: str)`.
  - `cargar_eval(path: str | Path) -> Eval`.

- [ ] **Step 1: Write the failing tests**

`tests/evals/__init__.py` queda vacío; si `tests/` no tiene `__init__.py`, no crees éste tampoco. Revisá con `ls tests/__init__.py` y seguí la misma convención.

`tests/evals/test_formato.py`:

```python
"""Carga y validación de `*.eval.yaml`."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from astromesh.evals.formato import EvalError, cargar_eval

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "vscode-extension/schemas/eval.schema.json").read_text()
)


def _doc(**spec):
    base = {
        "agent": "lucia",
        "thresholds": {"pass_rate": 0.9},
        "cases": [{"id": "c1", "turns": ["hola"], "expect": [{"contains": "hola"}]}],
    }
    base.update(spec)
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Eval",
        "metadata": {"name": "lucia-basico"},
        "spec": base,
    }


def _escribir(tmp_path, doc, nombre="e.eval.yaml"):
    p = tmp_path / nombre
    p.write_text(yaml.safe_dump(doc, allow_unicode=True))
    return p


def test_carga_un_eval_valido_con_cases_file(tmp_path):
    (tmp_path / "mas.jsonl").write_text(
        json.dumps({"id": "c2", "turns": ["a", "b"], "rubric": "bien"}) + "\n\n"
    )
    doc = _doc(
        judge={"model": {"provider": "ollama", "model": "llama3"}},
        tools_default="block",
        cases_file="mas.jsonl",
    )
    doc["spec"]["thresholds"]["max_avg_tokens"] = 6000
    ev = cargar_eval(_escribir(tmp_path, doc))
    assert ev.name == "lucia-basico" and ev.agent == "lucia"
    assert [c.id for c in ev.casos] == ["c1", "c2"]
    assert ev.casos[1].turns == ["a", "b"] and ev.casos[1].rubric == "bien"
    assert ev.tools_default == "block" and ev.max_avg_tokens == 6000
    assert ev.judge_model == {"provider": "ollama", "model": "llama3"}
    assert ev.judge_pass_score == 0.7
    assert ev.casos[0].context == {} and ev.casos[0].tools == {}


@pytest.mark.parametrize(
    "mutar, fragmento",
    [
        (lambda d: d["spec"]["cases"].append(dict(d["spec"]["cases"][0])), "duplicado"),
        (lambda d: d["spec"]["cases"][0].update(expect=[{"parece": "x"}]), "parece"),
        (lambda d: d["spec"]["cases"][0].update(rubric="r"), "judge"),
        (lambda d: d["spec"]["cases"][0].pop("expect"), "expect"),
        (lambda d: d["spec"]["thresholds"].update(pass_rate=1.5), "pass_rate"),
        (lambda d: d["spec"]["thresholds"].pop("pass_rate"), "pass_rate"),
        (lambda d: d["spec"].update(cases=[]), "al menos un caso"),
        (lambda d: d["spec"]["cases"][0].update(id="Con Espacio"), "id"),
        (lambda d: d["spec"]["cases"][0].update(turns=[]), "turns"),
        (lambda d: d["spec"].update(tools_default="a veces"), "tools_default"),
        (lambda d: d["spec"].update(otra=1), "otra"),
        (lambda d: d.update(kind="Agent"), "kind"),
    ],
)
def test_formas_invalidas_son_error_de_carga(tmp_path, mutar, fragmento):
    doc = _doc()
    mutar(doc)
    with pytest.raises(EvalError, match=fragmento):
        cargar_eval(_escribir(tmp_path, doc))


def test_regex_invalida_es_error_de_carga(tmp_path):
    doc = _doc()
    doc["spec"]["cases"][0]["expect"] = [{"regex": "("}]
    with pytest.raises(EvalError, match="regex"):
        cargar_eval(_escribir(tmp_path, doc))


def test_yaml_roto_es_error_de_carga(tmp_path):
    p = tmp_path / "roto.eval.yaml"
    p.write_text("spec: [")
    with pytest.raises(EvalError):
        cargar_eval(p)


def test_el_ejemplo_valida_contra_el_schema():
    doc = _doc(judge={"model": {"provider": "ollama", "model": "llama3"}, "pass_score": 0.8})
    doc["spec"]["cases"][0].update(
        context={"k": 1}, tools={"t": {"a": 1}}, rubric="r", expect=[{"tool_called": "t"}]
    )
    jsonschema.validate(doc, SCHEMA)


@pytest.mark.parametrize(
    "mutar",
    [
        lambda d: d["spec"]["cases"][0].update(expect=[{"parece": "x"}]),
        lambda d: d["spec"]["thresholds"].update(pass_rate=1.5),
        lambda d: d["spec"].update(otra=1),
    ],
)
def test_el_schema_rechaza_las_mismas_formas(mutar):
    doc = _doc()
    mutar(doc)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/test_formato.py -q`
Expected: FAIL, por `ModuleNotFoundError: astromesh.evals`.

- [ ] **Step 3: Write the implementation**

`astromesh/evals/__init__.py`:

```python
"""Evals de agentes: formato `kind: Eval` y runner (`astromesh-eval`).

`api.main` no importa este paquete: es una herramienta del autor y de CI.
"""
```

`astromesh/evals/formato.py`:

```python
"""Carga y valida un `*.eval.yaml`.

`vscode-extension/schemas/eval.schema.json` describe la misma forma para el editor;
acá se valida en Python porque `jsonschema` no es dependencia del core.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class EvalError(ValueError):
    """El eval no se puede cargar: el runner sale con 2 sin correr casos."""


ASSERTS = frozenset(
    {"contains", "not_contains", "regex", "equals", "tool_called", "tool_not_called"}
)
_ID = re.compile(r"^[a-z0-9_-]{1,64}$")
_CLAVES_SPEC = {"agent", "judge", "tools_default", "thresholds", "cases", "cases_file"}
_CLAVES_CASO = {"id", "turns", "context", "tools", "expect", "rubric"}


@dataclass(frozen=True)
class Caso:
    id: str
    turns: list[str]
    context: dict = field(default_factory=dict)
    tools: dict = field(default_factory=dict)
    expect: list[dict] = field(default_factory=list)
    rubric: str | None = None


@dataclass(frozen=True)
class Eval:
    name: str
    agent: str
    pass_rate: float
    casos: list[Caso]
    max_avg_tokens: int | None = None
    tools_default: str = "real"
    judge_model: dict | None = None
    judge_pass_score: float = 0.7
    path: str = ""


def _fraccion(valor) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool) and 0 <= valor <= 1


def _sobrantes(d: dict, permitidas: set[str], donde: str) -> None:
    sobran = sorted(set(d) - permitidas)
    if sobran:
        raise EvalError(f"{donde}: claves desconocidas {sobran}")


def _caso(crudo, donde: str, hay_juez: bool) -> Caso:
    if not isinstance(crudo, dict):
        raise EvalError(f"{donde}: un caso tiene que ser un mapa")
    _sobrantes(crudo, _CLAVES_CASO, donde)
    cid = crudo.get("id")
    if not isinstance(cid, str) or not _ID.match(cid):
        raise EvalError(f"{donde}: id {cid!r} inválido (usar [a-z0-9_-], hasta 64)")
    donde = f"{donde} caso {cid!r}"
    turns = crudo.get("turns")
    if not isinstance(turns, list) or not turns or not all(isinstance(t, str) for t in turns):
        raise EvalError(f"{donde}: turns tiene que ser una lista no vacía de strings")
    for clave in ("context", "tools"):
        if not isinstance(crudo.get(clave, {}), dict):
            raise EvalError(f"{donde}: {clave} tiene que ser un mapa")
    expect = crudo.get("expect", [])
    if not isinstance(expect, list):
        raise EvalError(f"{donde}: expect tiene que ser una lista")
    for a in expect:
        if not isinstance(a, dict) or len(a) != 1:
            raise EvalError(f"{donde}: cada assert es un mapa de una sola clave")
        ((clave, valor),) = a.items()
        if clave not in ASSERTS:
            raise EvalError(f"{donde}: assert desconocido {clave!r}")
        if not isinstance(valor, str) or not valor:
            raise EvalError(f"{donde}: el assert {clave!r} necesita un string")
        if clave == "regex":
            try:
                re.compile(valor)
            except re.error as exc:
                raise EvalError(f"{donde}: regex inválida {valor!r}: {exc}") from exc
    rubric = crudo.get("rubric")
    if rubric is not None and (not isinstance(rubric, str) or not rubric.strip()):
        raise EvalError(f"{donde}: rubric tiene que ser un string no vacío")
    if not expect and rubric is None:
        raise EvalError(f"{donde}: sin expect ni rubric, el caso no puede fallar")
    if rubric is not None and not hay_juez:
        raise EvalError(f"{donde}: tiene rubric pero el eval no declara judge")
    return Caso(
        id=cid,
        turns=list(turns),
        context=dict(crudo.get("context", {})),
        tools=dict(crudo.get("tools", {})),
        expect=list(expect),
        rubric=rubric,
    )


def _casos_de_archivo(path: Path, donde: str) -> list:
    if not path.is_file():
        raise EvalError(f"{donde}: no existe cases_file {str(path)!r}")
    crudos = []
    for n, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            crudos.append(json.loads(linea))
        except json.JSONDecodeError as exc:
            raise EvalError(f"{donde}: {path.name}:{n} no es JSON: {exc}") from exc
    return crudos


def cargar_eval(path) -> Eval:
    path = Path(path)
    donde = str(path)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvalError(f"{donde}: no se pudo leer: {exc}") from exc
    if not isinstance(doc, dict):
        raise EvalError(f"{donde}: el documento tiene que ser un mapa")
    if doc.get("apiVersion") != "astromesh/v1":
        raise EvalError(f"{donde}: apiVersion tiene que ser astromesh/v1")
    if doc.get("kind") != "Eval":
        raise EvalError(f"{donde}: kind tiene que ser Eval")
    nombre = (doc.get("metadata") or {}).get("name")
    if not isinstance(nombre, str) or not nombre:
        raise EvalError(f"{donde}: falta metadata.name")
    spec = doc.get("spec")
    if not isinstance(spec, dict):
        raise EvalError(f"{donde}: falta spec")
    _sobrantes(spec, _CLAVES_SPEC, f"{donde} spec")

    agente = spec.get("agent")
    if not isinstance(agente, str) or not agente:
        raise EvalError(f"{donde}: falta spec.agent")

    umbrales = spec.get("thresholds")
    if not isinstance(umbrales, dict):
        raise EvalError(f"{donde}: falta spec.thresholds.pass_rate")
    _sobrantes(umbrales, {"pass_rate", "max_avg_tokens"}, f"{donde} thresholds")
    if not _fraccion(umbrales.get("pass_rate")):
        raise EvalError(f"{donde}: thresholds.pass_rate tiene que estar entre 0 y 1")
    max_avg = umbrales.get("max_avg_tokens")
    if max_avg is not None and (
        not isinstance(max_avg, int) or isinstance(max_avg, bool) or max_avg < 1
    ):
        raise EvalError(f"{donde}: thresholds.max_avg_tokens tiene que ser un entero >= 1")

    tools_default = spec.get("tools_default", "real")
    if tools_default not in ("real", "block"):
        raise EvalError(f"{donde}: tools_default tiene que ser real o block")

    juez = spec.get("judge")
    pass_score = 0.7
    if juez is not None:
        if not isinstance(juez, dict) or not isinstance(juez.get("model"), dict):
            raise EvalError(f"{donde}: judge necesita un model")
        _sobrantes(juez, {"model", "pass_score"}, f"{donde} judge")
        pass_score = juez.get("pass_score", 0.7)
        if not _fraccion(pass_score):
            raise EvalError(f"{donde}: judge.pass_score tiene que estar entre 0 y 1")

    crudos = spec.get("cases", [])
    if not isinstance(crudos, list):
        raise EvalError(f"{donde}: cases tiene que ser una lista")
    crudos = list(crudos)
    if spec.get("cases_file") is not None:
        crudos += _casos_de_archivo(path.parent / str(spec["cases_file"]), donde)
    if not crudos:
        raise EvalError(f"{donde}: hace falta al menos un caso")
    casos = [_caso(c, donde, juez is not None) for c in crudos]
    vistos: set[str] = set()
    for c in casos:
        if c.id in vistos:
            raise EvalError(f"{donde}: id de caso duplicado {c.id!r}")
        vistos.add(c.id)

    return Eval(
        name=nombre,
        agent=agente,
        pass_rate=float(umbrales["pass_rate"]),
        casos=casos,
        max_avg_tokens=max_avg,
        tools_default=tools_default,
        judge_model=dict(juez["model"]) if juez else None,
        judge_pass_score=float(pass_score),
        path=donde,
    )
```

`vscode-extension/schemas/eval.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://astromesh.dev/schemas/eval.schema.json",
  "title": "Astromesh Eval",
  "type": "object",
  "required": ["apiVersion", "kind", "metadata", "spec"],
  "additionalProperties": false,
  "properties": {
    "apiVersion": {"const": "astromesh/v1"},
    "kind": {"const": "Eval"},
    "metadata": {
      "type": "object",
      "required": ["name"],
      "properties": {"name": {"type": "string", "minLength": 1}}
    },
    "spec": {
      "type": "object",
      "required": ["agent", "thresholds"],
      "additionalProperties": false,
      "properties": {
        "agent": {"type": "string", "minLength": 1, "description": "Agente del mismo árbol de config."},
        "judge": {
          "type": "object",
          "required": ["model"],
          "additionalProperties": false,
          "properties": {
            "model": {"type": "object", "description": "Misma forma que un candidato de model en un agente."},
            "pass_score": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.7}
          }
        },
        "tools_default": {"enum": ["real", "block"], "default": "real"},
        "thresholds": {
          "type": "object",
          "required": ["pass_rate"],
          "additionalProperties": false,
          "properties": {
            "pass_rate": {"type": "number", "minimum": 0, "maximum": 1},
            "max_avg_tokens": {"type": "integer", "minimum": 1}
          }
        },
        "cases": {"type": "array", "items": {"$ref": "#/$defs/caso"}},
        "cases_file": {"type": "string", "minLength": 1, "description": "JSONL relativo al eval, un caso por línea."}
      }
    }
  },
  "$defs": {
    "caso": {
      "type": "object",
      "required": ["id", "turns"],
      "additionalProperties": false,
      "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9_-]{1,64}$"},
        "turns": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "context": {"type": "object"},
        "tools": {"type": "object", "description": "Fixture por nombre de tool: no se ejecuta y devuelve esto."},
        "expect": {"type": "array", "items": {"$ref": "#/$defs/assert"}},
        "rubric": {"type": "string", "minLength": 1}
      }
    },
    "assert": {
      "type": "object",
      "minProperties": 1,
      "maxProperties": 1,
      "additionalProperties": false,
      "properties": {
        "contains": {"type": "string", "minLength": 1},
        "not_contains": {"type": "string", "minLength": 1},
        "regex": {"type": "string", "minLength": 1},
        "equals": {"type": "string", "minLength": 1},
        "tool_called": {"type": "string", "minLength": 1},
        "tool_not_called": {"type": "string", "minLength": 1}
      }
    }
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/evals/test_formato.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check astromesh/evals tests/evals && uv run ruff format --check astromesh/evals tests/evals
git add astromesh/evals tests/evals vscode-extension/schemas/eval.schema.json
git commit -m "feat(evals): formato kind: Eval — cargador y schema"
```

(El changelog va con el commit `feat:` del Task 6, que cierra el feature. Este commit queda en la rama hasta entonces.)

---

### Task 2: Asserts

**Files:**
- Create: `astromesh/evals/asserts.py`
- Test: `tests/evals/test_asserts.py`

**Interfaces:**
- Consumes: la forma de un assert de Task 1 (mapa de una clave de `ASSERTS` a un string).
- Produces: `chequear(asercion: dict, respuesta: str, tools_llamadas: list[str]) -> str | None`. Devuelve `None` si pasa y el motivo si no.

- [ ] **Step 1: Write the failing tests**

```python
"""Cada assert pasa y falla."""

import pytest

from astromesh.evals.asserts import chequear


@pytest.mark.parametrize(
    "asercion, respuesta, tools, pasa",
    [
        ({"contains": "DOCE"}, "hay doce unidades", [], True),
        ({"contains": "trece"}, "hay doce unidades", [], False),
        ({"not_contains": "no sé"}, "hay 12", [], True),
        ({"not_contains": "NO SÉ"}, "no sé", [], False),
        ({"regex": r"\b12\b"}, "hay 12", [], True),
        ({"regex": "Hay"}, "hay 12", [], False),
        ({"regex": "(?i)HAY"}, "hay 12", [], True),
        ({"equals": "ok"}, "  ok\n", [], True),
        ({"equals": "ok"}, "ok.", [], False),
        ({"tool_called": "stock"}, "", ["precio", "stock"], True),
        ({"tool_called": "stock"}, "", ["precio"], False),
        ({"tool_not_called": "borrar"}, "", ["stock"], True),
        ({"tool_not_called": "borrar"}, "", ["borrar"], False),
    ],
)
def test_chequear(asercion, respuesta, tools, pasa):
    motivo = chequear(asercion, respuesta, tools)
    assert (motivo is None) is pasa
    if not pasa:
        assert isinstance(motivo, str) and motivo
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/test_asserts.py -q`
Expected: FAIL, por `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
"""Asserts deterministas de un caso. Puros: no saben del runtime."""

from __future__ import annotations

import re


def chequear(asercion: dict, respuesta: str, tools_llamadas: list[str]) -> str | None:
    """None si el assert pasa; si no, el motivo para el reporte."""
    ((clave, valor),) = asercion.items()
    if clave == "contains":
        return None if valor.lower() in respuesta.lower() else f"no contiene {valor!r}"
    if clave == "not_contains":
        return f"contiene {valor!r}" if valor.lower() in respuesta.lower() else None
    if clave == "regex":
        return None if re.search(valor, respuesta) else f"no coincide con /{valor}/"
    if clave == "equals":
        return None if respuesta.strip() == valor else f"no es igual a {valor!r}"
    if clave == "tool_called":
        return None if valor in tools_llamadas else f"no llamó a la tool {valor!r}"
    if clave == "tool_not_called":
        return f"llamó a la tool {valor!r}" if valor in tools_llamadas else None
    raise ValueError(f"assert desconocido {clave!r}")  # formato.py ya lo rechaza al cargar
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/evals/test_asserts.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check astromesh/evals tests/evals && uv run ruff format --check astromesh/evals tests/evals
git add astromesh/evals/asserts.py tests/evals/test_asserts.py
git commit -m "feat(evals): asserts deterministas"
```

---

### Task 3: Memoria aislada y fixtures de tools

**Files:**
- Create: `astromesh/evals/memoria.py`
- Create: `astromesh/evals/fixtures.py`
- Test: `tests/evals/test_fixtures_memoria.py`

**Interfaces:**
- Consumes: `ConversationBackend` (`astromesh/core/memory.py:39`), que es un ABC con `save_turn`, `get_history(session_id, limit=50)`, `clear`, `get_summary` y `save_summary`. También `ToolRegistry.execute(tool_name, arguments, context=None) -> dict` (`astromesh/core/tools.py:196`).
- Produces:
  - `MemoriaDeEval(ConversationBackend)`.
  - `EstadoCaso(fixtures: dict, bloquear: bool, llamadas: list[str])`.
  - `instalar(registry) -> None`, idempotente.
  - `caso(fixtures: dict, bloquear: bool)`: context manager que hace yield de `EstadoCaso`.
  - `preparar(runtime) -> None`: instala el wrapper en el registry de cada agente y le pone `MemoriaDeEval` a cada agente que declara `memory.conversational`.

**Notas para el implementador:**
- Cada agente tiene su propio `ToolRegistry` (`engine.py:907`, `tools = ToolRegistry()`), en `agent._tools`.
- La memoria es `agent._memory`, un `MemoryManager`. Su backend conversacional es `agent._memory._conversation`, y su config (el bloque `memory` del manifiesto) es `agent._memory.config`.
- El motor llama `self._tools.execute(name, args, {...})` desde `tool_fn` (`engine.py:1923`). Reemplazar el atributo `execute` en la instancia alcanza.

- [ ] **Step 1: Write the failing tests**

```python
"""Fixtures de tools por caso y memoria aislada del eval."""

import yaml

from astromesh.core import tokens
from astromesh.core.tools import ToolRegistry
from astromesh.evals import fixtures
from astromesh.evals.memoria import MemoriaDeEval
from astromesh.runtime.engine import AgentRuntime

import pytest


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


def _registry():
    reg = ToolRegistry()
    llamadas = []

    async def real(**kw):
        llamadas.append(kw)
        return {"real": True}

    reg.register_internal(
        name="stock", handler=real, description="d", parameters={"type": "object"}
    )
    return reg, llamadas


async def test_con_fixture_no_ejecuta_y_devuelve_el_valor():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({"stock": {"stock": 12}}, bloquear=False) as estado:
        assert await reg.execute("stock", {}) == {"stock": 12}
    assert llamadas == [] and estado.llamadas == ["stock"]


async def test_valor_no_dict_se_envuelve():
    reg, _ = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({"stock": 12}, bloquear=False):
        assert await reg.execute("stock", {}) == {"result": 12}


async def test_block_sin_fixture_devuelve_error_y_no_ejecuta():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({}, bloquear=True):
        assert await reg.execute("stock", {}) == {"error": "tool sin fixture en el eval: stock"}
    assert llamadas == []


async def test_real_sin_fixture_ejecuta():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    with fixtures.caso({}, bloquear=False) as estado:
        assert await reg.execute("stock", {"sku": "X"}) == {"real": True}
    assert llamadas == [{"sku": "X"}] and estado.llamadas == ["stock"]


async def test_fuera_de_un_caso_ejecuta_la_real():
    reg, llamadas = _registry()
    fixtures.instalar(reg)
    assert await reg.execute("stock", {}) == {"real": True}
    assert len(llamadas) == 1


async def test_instalar_es_idempotente():
    reg, _ = _registry()
    fixtures.instalar(reg)
    fixtures.instalar(reg)
    with fixtures.caso({}, bloquear=False) as estado:
        await reg.execute("stock", {})
    assert estado.llamadas == ["stock"]  # una sola vez, no envuelta dos veces


async def test_fixture_se_devuelve_como_copia():
    reg, _ = _registry()
    fixtures.instalar(reg)
    fijo = {"stock": {"items": [1]}}
    with fixtures.caso(fijo, bloquear=False):
        (await reg.execute("stock", {}))["items"].append(2)
    with fixtures.caso(fijo, bloquear=False):
        assert await reg.execute("stock", {}) == {"items": [1]}


async def test_memoria_separa_sesiones():
    from datetime import UTC, datetime

    from astromesh.core.memory import ConversationTurn

    m = MemoriaDeEval()
    t = ConversationTurn(role="user", content="hola", timestamp=datetime.now(UTC))
    await m.save_turn("a", t)
    assert [x.content for x in await m.get_history("a")] == ["hola"]
    assert await m.get_history("b") == []
    await m.save_summary("a", "res")
    assert await m.get_summary("a") == "res" and await m.get_summary("b") is None
    await m.clear("a")
    assert await m.get_history("a") == []


async def test_preparar_aisla_memoria_e_instala_fixtures(tmp_path):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    for nombre, memoria in (("con-mem", True), ("sin-mem", False)):
        spec = {
            "identity": {"description": "demo"},
            "model": {"primary": {"provider": "ollama", "model": "llama3"}},
            "prompts": {"system": "sos un agente"},
        }
        if memoria:
            spec["memory"] = {
                "conversational": {
                    "backend": "redis",
                    "connection": {"url": "redis://localhost:1"},
                    "strategy": "sliding_window",
                }
            }
        (d / "agents" / f"{nombre}.agent.yaml").write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "astromesh/v1",
                    "kind": "Agent",
                    "metadata": {"name": nombre, "version": "0.1.0"},
                    "spec": spec,
                }
            )
        )
    rt = AgentRuntime(config_dir=str(d))
    await rt.bootstrap()
    assert set(rt._agents) == {"con-mem", "sin-mem"}, rt._agent_errors
    fixtures.preparar(rt)
    assert isinstance(rt._agents["con-mem"]._memory._conversation, MemoriaDeEval)
    assert not isinstance(rt._agents["sin-mem"]._memory._conversation, MemoriaDeEval)
    for agente in rt._agents.values():
        assert getattr(agente._tools, "_eval_fixtures", False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/test_fixtures_memoria.py -q`
Expected: FAIL, por `ImportError`.

- [ ] **Step 3: Write the implementation**

`astromesh/evals/memoria.py`:

```python
"""Backend conversacional en memoria: un eval nunca escribe en Redis ni Postgres."""

from __future__ import annotations

from collections import defaultdict

from astromesh.core.memory import ConversationBackend


class MemoriaDeEval(ConversationBackend):
    def __init__(self):
        self._turnos: dict[str, list] = defaultdict(list)
        self._resumenes: dict[str, str] = {}

    async def save_turn(self, session_id, turn):
        self._turnos[session_id].append(turn)

    async def get_history(self, session_id, limit=50):
        return list(self._turnos.get(session_id, [])[-limit:])

    async def clear(self, session_id):
        self._turnos.pop(session_id, None)
        self._resumenes.pop(session_id, None)

    async def get_summary(self, session_id):
        return self._resumenes.get(session_id)

    async def save_summary(self, session_id, summary):
        self._resumenes[session_id] = summary
```

`astromesh/evals/fixtures.py`:

```python
"""Fixtures de tools por caso.

El runner envuelve una vez el `execute` del `ToolRegistry` de cada agente. Las fixtures
del caso viajan en un ContextVar, así que un sub-agente llamado como tool —que corre en
el mismo contexto— también queda stubeado. El recorte de 0.66 (`presentar`) y el gate de
confirmación (en `tool_fn`) siguen aplicando: ocurren antes y después de `execute`.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from astromesh.evals.memoria import MemoriaDeEval


@dataclass
class EstadoCaso:
    fixtures: dict
    bloquear: bool
    llamadas: list[str] = field(default_factory=list)


_CASO: ContextVar[EstadoCaso | None] = ContextVar("astromesh_eval_caso", default=None)


def instalar(registry) -> None:
    if getattr(registry, "_eval_fixtures", False):
        return
    original = registry.execute

    async def execute(tool_name, arguments, context=None):
        estado = _CASO.get()
        if estado is None:
            return await original(tool_name, arguments, context)
        estado.llamadas.append(tool_name)
        if tool_name in estado.fixtures:
            valor = copy.deepcopy(estado.fixtures[tool_name])
            return valor if isinstance(valor, dict) else {"result": valor}
        if estado.bloquear:
            return {"error": f"tool sin fixture en el eval: {tool_name}"}
        return await original(tool_name, arguments, context)

    registry.execute = execute
    registry._eval_fixtures = True


@contextmanager
def caso(fixtures: dict, bloquear: bool) -> Iterator[EstadoCaso]:
    estado = EstadoCaso(fixtures=dict(fixtures), bloquear=bloquear)
    token = _CASO.set(estado)
    try:
        yield estado
    finally:
        _CASO.reset(token)


def preparar(runtime) -> None:
    """Fixtures en todos los agentes y memoria aislada en los que declaran conversacional."""
    for agente in runtime._agents.values():
        instalar(agente._tools)
        memoria = getattr(agente, "_memory", None)
        if memoria is not None and "conversational" in (memoria.config or {}):
            memoria._conversation = MemoriaDeEval()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/evals/test_fixtures_memoria.py -q`
Expected: PASS. Si `register_internal` exige otros argumentos, mirá su firma en `astromesh/core/tools.py:91` y ajustá **el test**, no la firma.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check astromesh/evals tests/evals && uv run ruff format --check astromesh/evals tests/evals
git add astromesh/evals/memoria.py astromesh/evals/fixtures.py tests/evals/test_fixtures_memoria.py
git commit -m "feat(evals): memoria aislada y fixtures de tools por caso"
```

---

### Task 4: Juez LLM

**Files:**
- Create: `astromesh/evals/juez.py`
- Test: `tests/evals/test_juez.py`

**Interfaces:**
- Consumes: un provider con `async complete(messages: list[dict], **kw) -> CompletionResponse`. La respuesta trae `.content: str` y `.usage: dict`, que puede tener `input_tokens` y `output_tokens` (`astromesh/providers/base.py`).
- Produces:
  - `Veredicto(score: float | None, reason: str, tokens: int, error: str | None)`.
  - `async juzgar(provider, rubrica: str, turnos: list[str], respuesta: str) -> Veredicto`. Nunca levanta. `error` no es `None` cuando no hubo un veredicto válido, y entonces el caso queda en `error`.

- [ ] **Step 1: Write the failing tests**

```python
"""El juez: veredicto, respuestas inválidas y tokens aparte."""

from astromesh.evals.juez import juzgar
from astromesh.providers.base import CompletionResponse


class _Juez:
    def __init__(self, contenido=None, levanta=False):
        self.contenido, self.levanta, self.mensajes = contenido, levanta, None

    async def complete(self, messages, **kw):
        self.mensajes = messages
        if self.levanta:
            raise RuntimeError("caído")
        return CompletionResponse(
            content=self.contenido,
            model="j",
            provider="p",
            usage={"input_tokens": 30, "output_tokens": 5},
            latency_ms=1.0,
            cost=0.0,
        )


async def test_veredicto_valido_y_prompt_con_rubrica():
    j = _Juez('{"score": 0.8, "reason": "bien"}')
    v = await juzgar(j, "dice la cantidad", ["¿stock?"], "hay 12")
    assert (v.score, v.reason, v.tokens, v.error) == (0.8, "bien", 35, None)
    texto = j.mensajes[-1]["content"]
    assert "dice la cantidad" in texto and "¿stock?" in texto and "hay 12" in texto


async def test_acepta_json_en_fence():
    v = await juzgar(_Juez('```json\n{"score": 1, "reason": "ok"}\n```'), "r", ["q"], "a")
    assert v.score == 1.0 and v.error is None


async def test_no_json_es_error():
    v = await juzgar(_Juez("me parece bien"), "r", ["q"], "a")
    assert v.score is None and v.error


async def test_score_fuera_de_rango_es_error():
    v = await juzgar(_Juez('{"score": 7, "reason": "x"}'), "r", ["q"], "a")
    assert v.score is None and v.error


async def test_provider_que_levanta_es_error():
    v = await juzgar(_Juez(levanta=True), "r", ["q"], "a")
    assert v.score is None and "caído" in v.error and v.tokens == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/test_juez.py -q`
Expected: FAIL, por `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
"""Juez LLM de los casos con `rubric`. Nunca levanta: un veredicto inválido es `error`."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_SISTEMA = (
    "Sos un evaluador estricto. Juzgás si la respuesta de un agente cumple una rúbrica. "
    'Respondé SÓLO con JSON: {"score": <número entre 0 y 1>, "reason": "<una oración>"}.'
)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


@dataclass(frozen=True)
class Veredicto:
    score: float | None
    reason: str
    tokens: int
    error: str | None


def _prompt(rubrica: str, turnos: list[str], respuesta: str) -> str:
    usuario = "\n".join(f"- {t}" for t in turnos)
    return (
        f"RÚBRICA:\n{rubrica}\n\nMENSAJES DEL USUARIO:\n{usuario}\n\n"
        f"RESPUESTA DEL AGENTE:\n{respuesta}"
    )


async def juzgar(provider, rubrica: str, turnos: list[str], respuesta: str) -> Veredicto:
    mensajes = [
        {"role": "system", "content": _SISTEMA},
        {"role": "user", "content": _prompt(rubrica, turnos, respuesta)},
    ]
    try:
        r = await provider.complete(mensajes)
    except Exception as exc:  # noqa: BLE001  (el juez caído deja el caso en error, no corta)
        return Veredicto(None, "", 0, f"el juez falló: {type(exc).__name__}: {exc}")
    usage = r.usage or {}
    tokens = int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0)
    texto = (r.content or "").strip()
    m = _FENCE.match(texto)
    if m:
        texto = m.group(1)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return Veredicto(None, "", tokens, f"el juez no devolvió JSON: {texto[:200]!r}")
    score = datos.get("score") if isinstance(datos, dict) else None
    if not isinstance(score, int | float) or isinstance(score, bool) or not 0 <= score <= 1:
        return Veredicto(None, "", tokens, f"score inválido del juez: {score!r}")
    return Veredicto(float(score), str(datos.get("reason", "")), tokens, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/evals/test_juez.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check astromesh/evals tests/evals && uv run ruff format --check astromesh/evals tests/evals
git add astromesh/evals/juez.py tests/evals/test_juez.py
git commit -m "feat(evals): juez LLM con veredicto validado"
```

---

### Task 5: Runner — correr un eval contra el runtime

**Files:**
- Create: `astromesh/evals/runner.py`
- Test: `tests/evals/test_runner.py`

**Interfaces:**
- Consumes:
  - `Eval` y `Caso` (Task 1), `chequear` (Task 2), `fixtures.caso` y `fixtures.preparar` (Task 3), `juzgar` (Task 4).
  - `AgentRuntime.run(agent_name, query, session_id, context=None) -> dict`, con `answer` y `trace`.
  - `usage_from_trace(trace) -> dict | None` (`astromesh/api/usage.py:30`), con `tokens_in`, `tokens_out` y `by_model[]`; cada fila de `by_model` trae `tokens_cached` y `cost`.
- Produces: `async correr_eval(runtime, ev: Eval, run_id: str, juez=None) -> dict`. El dict es un eval del reporte con `name`, `agent`, `passed`, `pass_rate`, `avg_tokens`, `total_cost` y `cases`. Cada caso es un dict con `id`, `status`, `motivos`, `judge`, `tokens_in`, `tokens_out`, `cached_tokens`, `cost`, `latency_ms`, `judge_tokens`, `tools_llamadas` y `answer`. Requiere haber llamado `fixtures.preparar(runtime)` antes.

- [ ] **Step 1: Write the failing tests**

```python
"""correr_eval: estados por caso, memoria entre turnos, umbrales y uso."""

import pytest
import yaml

from astromesh.core import tokens
from astromesh.evals import fixtures
from astromesh.evals.formato import Caso, Eval
from astromesh.evals.runner import correr_eval
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime
from astromesh.tools import ToolLoader
from astromesh.tools.base import BuiltinTool, ToolContext, ToolResult

EJECUCIONES = []


class _Stock(BuiltinTool):
    name = "stock"
    description = "stock de un sku"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        EJECUCIONES.append(arguments)
        return ToolResult(success=True, data={"stock": 99}, metadata={})


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)
    monkeypatch.setattr(ToolLoader, "auto_discover", lambda self: self.register_class(_Stock))
    EJECUCIONES.clear()


def _resp(content="", tool_calls=None, usage=None, cost=0.0):
    return CompletionResponse(
        content=content,
        model="m",
        provider="p",
        usage=usage or {},
        latency_ms=1.0,
        cost=cost,
        tool_calls=tool_calls or [],
    )


async def _runtime(tmp_path):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    (d / "agents" / "lucia.agent.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "lucia", "version": "0.1.0"},
                "spec": {
                    "identity": {"description": "demo"},
                    "model": {"primary": {"provider": "ollama", "model": "llama3"}},
                    "prompts": {"system": "sos un agente"},
                    "orchestration": {"pattern": "react"},
                    "tools": [{"name": "stock", "type": "builtin"}],
                    "memory": {
                        "conversational": {
                            "backend": "redis",
                            "connection": {"url": "redis://localhost:1"},
                            "strategy": "sliding_window",
                        }
                    },
                },
            }
        )
    )
    rt = AgentRuntime(config_dir=str(d))
    await rt.bootstrap()
    assert "lucia" in rt._agents, rt._agent_errors
    fixtures.preparar(rt)
    return rt


def _modelo(rt, fn):
    rt._agents["lucia"]._routers["default"].route = fn


def _eval(casos, **kw):
    return Eval(name="e", agent="lucia", pass_rate=kw.pop("pass_rate", 1.0), casos=casos, **kw)


async def test_fixture_tool_called_y_uso(tmp_path):
    rt = await _runtime(tmp_path)
    vistos = []

    async def route(messages, requirements=None, **kw):
        vistos.append(list(messages))
        if len(vistos) == 1:
            return _resp(
                tool_calls=[{"id": "t1", "name": "stock", "arguments": {}}],
                usage={"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 40},
                cost=0.01,
            )
        return _resp("hay 12", usage={"input_tokens": 120, "output_tokens": 5}, cost=0.02)

    _modelo(rt, route)
    caso = Caso(
        id="c1",
        turns=["¿stock?"],
        tools={"stock": {"stock": 12}},
        expect=[{"contains": "12"}, {"tool_called": "stock"}],
    )
    r = await correr_eval(rt, _eval([caso]), "run1")
    c = r["cases"][0]
    assert c["status"] == "pass", c["motivos"]
    assert EJECUCIONES == []  # la fixture no ejecutó la tool real
    assert any("12" in str(m.get("content")) for m in vistos[1] if m.get("role") == "tool")
    assert (c["tokens_in"], c["tokens_out"], c["cached_tokens"]) == (220, 15, 40)
    assert c["cost"] == pytest.approx(0.03)
    assert c["tools_llamadas"] == ["stock"] and c["answer"] == "hay 12"
    assert r["passed"] is True and r["pass_rate"] == 1.0 and r["avg_tokens"] == 235


async def test_turnos_comparten_memoria_y_casos_no(tmp_path):
    rt = await _runtime(tmp_path)
    vistos = []

    async def route(messages, requirements=None, **kw):
        vistos.append([m.get("content") for m in messages])
        return _resp("ok")

    _modelo(rt, route)
    casos = [
        Caso(id="a", turns=["me llamo Ana", "¿cómo me llamo?"], expect=[{"contains": "ok"}]),
        Caso(id="b", turns=["¿cómo me llamo?"], expect=[{"contains": "ok"}]),
    ]
    await correr_eval(rt, _eval(casos), "run2")
    assert any("me llamo Ana" in str(c) for c in vistos[1])  # turno 2 de `a` ve el turno 1
    assert not any("me llamo Ana" in str(c) for c in vistos[2])  # `b` no ve a `a`


async def test_context_se_copia_por_turno(tmp_path):
    rt = await _runtime(tmp_path)
    recibidos = []
    original = rt.run

    async def run(agent_name, query, session_id, context=None, **kw):
        recibidos.append(context)
        context["mutado"] = True
        return await original(agent_name, query, session_id, context=context, **kw)

    rt.run = run
    _modelo(rt, lambda *a, **k: _async(_resp("ok")))
    caso = Caso(id="c", turns=["1", "2"], context={"k": 1}, expect=[{"contains": "ok"}])
    await correr_eval(rt, _eval([caso]), "run3")
    assert recibidos[1] == {"k": 1}


async def _async(valor):
    return valor


async def test_caso_que_levanta_queda_en_error_y_sigue(tmp_path):
    rt = await _runtime(tmp_path)
    llamadas = []

    async def route(messages, requirements=None, **kw):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("proveedor caído")
        return _resp("ok")

    _modelo(rt, route)
    casos = [
        Caso(id="a", turns=["x"], expect=[{"contains": "ok"}]),
        Caso(id="b", turns=["y"], expect=[{"contains": "ok"}]),
    ]
    r = await correr_eval(rt, _eval(casos, pass_rate=0.5), "run4")
    estados = [c["status"] for c in r["cases"]]
    assert estados[1] == "pass" and estados[0] in ("error", "fail")
    assert r["pass_rate"] == 0.5 and r["passed"] is True


async def test_umbrales_deciden_passed(tmp_path):
    rt = await _runtime(tmp_path)

    async def route(messages, requirements=None, **kw):
        return _resp("ok", usage={"input_tokens": 500, "output_tokens": 0})

    _modelo(rt, route)
    casos = [
        Caso(id="a", turns=["x"], expect=[{"contains": "ok"}]),
        Caso(id="b", turns=["y"], expect=[{"contains": "nunca"}]),
    ]
    r = await correr_eval(rt, _eval(casos, pass_rate=0.9), "run5")
    assert r["pass_rate"] == 0.5 and r["passed"] is False
    assert r["cases"][1]["status"] == "fail" and r["cases"][1]["motivos"]
    r = await correr_eval(rt, _eval(casos[:1], max_avg_tokens=100), "run6")
    assert r["passed"] is False  # pasa el caso, pero 500 tokens > 100


async def test_juez_decide_y_sus_tokens_van_aparte(tmp_path):
    rt = await _runtime(tmp_path)

    async def route(messages, requirements=None, **kw):
        return _resp("hay 12", usage={"input_tokens": 10, "output_tokens": 2})

    _modelo(rt, route)

    class Juez:
        def __init__(self, score):
            self.score = score

        async def complete(self, messages, **kw):
            return _resp(
                f'{{"score": {self.score}, "reason": "r"}}',
                usage={"input_tokens": 50, "output_tokens": 5},
            )

    caso = Caso(id="c", turns=["q"], rubric="dice 12")
    ev = _eval([caso], judge_model={"provider": "ollama"}, judge_pass_score=0.7)
    r = await correr_eval(rt, ev, "run7", juez=Juez(0.9))
    c = r["cases"][0]
    assert c["status"] == "pass" and c["judge"] == {"score": 0.9, "reason": "r"}
    assert c["judge_tokens"] == 55 and c["tokens_in"] + c["tokens_out"] == 12
    r = await correr_eval(rt, ev, "run8", juez=Juez(0.2))
    assert r["cases"][0]["status"] == "fail"


async def test_block_sin_fixture_no_ejecuta(tmp_path):
    rt = await _runtime(tmp_path)
    n = []

    async def route(messages, requirements=None, **kw):
        n.append(1)
        if len(n) == 1:
            return _resp(tool_calls=[{"id": "t1", "name": "stock", "arguments": {}}])
        return _resp("ok")

    _modelo(rt, route)
    caso = Caso(id="c", turns=["q"], expect=[{"tool_called": "stock"}])
    r = await correr_eval(rt, _eval([caso], tools_default="block"), "run9")
    assert r["cases"][0]["status"] == "pass" and EJECUCIONES == []
```

**Nota para el implementador.** Si `test_caso_que_levanta…` encuentra que el motor captura la excepción del router y devuelve una respuesta (no levanta), el caso termina en `fail` y no en `error`. El test acepta las dos.

**Nota de `test_context_se_copia_por_turno`.** Reemplaza `rt.run` con un wrapper que muta el contexto recibido. El runner tiene que llamar `runtime.run(...)` por atributo, no capturar el método antes, y pasar una copia profunda nueva en cada turno.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/test_runner.py -q`
Expected: FAIL, por `ModuleNotFoundError: astromesh.evals.runner`.

- [ ] **Step 3: Write the implementation**

```python
"""Corre un eval contra un AgentRuntime ya arrancado y `preparar`-ado.

Un caso nunca corta el eval: lo que levanta queda en `error` y cuenta como no aprobado.
"""

from __future__ import annotations

import copy
import time

from astromesh.api.usage import usage_from_trace
from astromesh.evals import fixtures
from astromesh.evals.asserts import chequear
from astromesh.evals.formato import Caso, Eval
from astromesh.evals.juez import juzgar


def _uso(trace) -> tuple[int, int, int, float]:
    u = usage_from_trace(trace) or {}
    filas = u.get("by_model") or []
    return (
        int(u.get("tokens_in", 0)),
        int(u.get("tokens_out", 0)),
        sum(int(f.get("tokens_cached", 0)) for f in filas),
        sum(float(f.get("cost", 0.0)) for f in filas),
    )


async def _correr_caso(runtime, ev: Eval, caso: Caso, run_id: str, juez) -> dict:
    session = f"eval-{run_id}-{caso.id}"
    r = {
        "id": caso.id,
        "status": "pass",
        "motivos": [],
        "judge": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "cached_tokens": 0,
        "cost": 0.0,
        "latency_ms": 0.0,
        "judge_tokens": 0,
        "tools_llamadas": [],
        "answer": "",
    }
    inicio = time.monotonic()
    with fixtures.caso(caso.tools, bloquear=ev.tools_default == "block") as estado:
        try:
            for turno in caso.turns:
                res = await runtime.run(
                    ev.agent, turno, session, context=copy.deepcopy(caso.context)
                )
                r["answer"] = (res or {}).get("answer") or ""
                tin, tout, cached, cost = _uso((res or {}).get("trace"))
                r["tokens_in"] += tin
                r["tokens_out"] += tout
                r["cached_tokens"] += cached
                r["cost"] += cost
        except Exception as exc:  # noqa: BLE001  (un caso que levanta no corta el eval)
            r["status"] = "error"
            r["motivos"].append(f"{type(exc).__name__}: {exc}")
        r["tools_llamadas"] = list(estado.llamadas)
    r["latency_ms"] = round((time.monotonic() - inicio) * 1000, 1)
    if r["status"] == "error":
        return r

    for asercion in caso.expect:
        motivo = chequear(asercion, r["answer"], r["tools_llamadas"])
        if motivo:
            r["motivos"].append(motivo)
    if caso.rubric is not None:
        v = await juzgar(juez, caso.rubric, caso.turns, r["answer"])
        r["judge_tokens"] = v.tokens
        if v.error:
            r["status"] = "error"
            r["motivos"].append(v.error)
            return r
        r["judge"] = {"score": v.score, "reason": v.reason}
        if v.score < ev.judge_pass_score:
            r["motivos"].append(f"el juez dio {v.score} (< {ev.judge_pass_score}): {v.reason}")
    if r["motivos"]:
        r["status"] = "fail"
    return r


async def correr_eval(runtime, ev: Eval, run_id: str, juez=None) -> dict:
    casos = [await _correr_caso(runtime, ev, c, run_id, juez) for c in ev.casos]
    aprobados = sum(1 for c in casos if c["status"] == "pass")
    pass_rate = aprobados / len(casos)
    avg_tokens = sum(c["tokens_in"] + c["tokens_out"] for c in casos) / len(casos)
    passed = pass_rate >= ev.pass_rate and (
        ev.max_avg_tokens is None or avg_tokens <= ev.max_avg_tokens
    )
    return {
        "name": ev.name,
        "agent": ev.agent,
        "passed": passed,
        "pass_rate": round(pass_rate, 4),
        "avg_tokens": round(avg_tokens, 1),
        "total_cost": round(sum(c["cost"] for c in casos), 6),
        "cases": casos,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/evals/test_runner.py -q`
Expected: PASS.

Si `test_fixture_tool_called_y_uso` falla en los tokens, imprimí `usage_from_trace(res["trace"])` para ver qué escribe el motor. Por ejemplo, si `cached_tokens` sale de `cache_read_input_tokens`, como en `engine.py:1825`, ajustá **el test** a lo que el motor reporta de verdad, no el motor.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check astromesh/evals tests/evals && uv run ruff format --check astromesh/evals tests/evals
git add astromesh/evals/runner.py tests/evals/test_runner.py
git commit -m "feat(evals): runner — casos, juez, uso y umbrales"
```

---

### Task 6: CLI `astromesh-eval`, entry point, changelog y guía

**Files:**
- Create: `astromesh/evals/__main__.py`
- Modify: `pyproject.toml` (sección nueva `[project.scripts]`, después de `[project.optional-dependencies]`)
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Modify: `docs/CONFIGURATION_GUIDE.md` (sección nueva al final, «Evals de agentes»)
- Test: `tests/evals/test_cli.py`

**Interfaces:**
- Consumes:
  - `cargar_eval` y `EvalError` (Task 1), `fixtures.preparar` (Task 3), `correr_eval` (Task 5).
  - `build_candidate_provider(block: dict)` (`astromesh/runtime/engine.py:393`), que devuelve un provider, o `None` si no lo puede construir.
  - `AgentRuntime(config_dir=...)`, `await runtime.bootstrap()`, `runtime._agents` y `runtime._agent_errors`.
- Produces: `main(argv: list[str] | None = None) -> int`, con exit code 0, 1 o 2. También `async correr(config_dir: str, evals: list[Eval], out: str | None) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
"""CLI: exit codes, --out, errores de carga."""

import json

import pytest
import yaml

from astromesh.core import tokens
from astromesh.evals import __main__ as cli
from astromesh.providers.base import CompletionResponse
from astromesh.runtime.engine import AgentRuntime


@pytest.fixture(autouse=True)
def sin_litellm(monkeypatch):
    monkeypatch.setattr(tokens, "_litellm", lambda: None)


@pytest.fixture
def modelo_ok(monkeypatch):
    """Todo agente arrancado responde 'ok' sin red."""
    original = AgentRuntime.bootstrap

    async def bootstrap(self):
        await original(self)
        for agente in self._agents.values():

            async def route(messages, requirements=None, **kw):
                return CompletionResponse(
                    content="ok",
                    model="m",
                    provider="p",
                    usage={"input_tokens": 7, "output_tokens": 1},
                    latency_ms=1.0,
                    cost=0.0,
                )

            agente._routers["default"].route = route

    monkeypatch.setattr(AgentRuntime, "bootstrap", bootstrap)


def _config(tmp_path, expect="ok", agente="lucia"):
    d = tmp_path / "config"
    (d / "agents").mkdir(parents=True)
    (d / "evals").mkdir()
    (d / "agents" / "lucia.agent.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Agent",
                "metadata": {"name": "lucia", "version": "0.1.0"},
                "spec": {
                    "identity": {"description": "demo"},
                    "model": {"primary": {"provider": "ollama", "model": "llama3"}},
                    "prompts": {"system": "sos un agente"},
                },
            }
        )
    )
    (d / "evals" / "e.eval.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "astromesh/v1",
                "kind": "Eval",
                "metadata": {"name": "e"},
                "spec": {
                    "agent": agente,
                    "thresholds": {"pass_rate": 1.0},
                    "cases": [{"id": "c", "turns": ["hola"], "expect": [{"contains": expect}]}],
                },
            }
        )
    )
    return d


def test_todo_pasa_sale_0_y_escribe_out(tmp_path, modelo_ok, capsys):
    d = _config(tmp_path)
    out = tmp_path / "r.json"
    assert cli.main([str(d), "--out", str(out)]) == 0
    rep = json.loads(out.read_text())
    assert set(rep) == {"run_id", "evals"}
    (ev,) = rep["evals"]
    assert ev["name"] == "e" and ev["passed"] is True and ev["cases"][0]["status"] == "pass"
    assert {"tokens_in", "cost", "latency_ms", "motivos"} <= set(ev["cases"][0])
    assert "e" in capsys.readouterr().out


def test_bajo_umbral_sale_1(tmp_path, modelo_ok):
    assert cli.main([str(_config(tmp_path, expect="nunca"))]) == 1


def test_agente_inexistente_sale_2_sin_correr(tmp_path, modelo_ok, capsys):
    assert cli.main([str(_config(tmp_path, agente="nadie"))]) == 2
    assert "nadie" in capsys.readouterr().err


def test_eval_invalido_sale_2(tmp_path):
    d = _config(tmp_path)
    (d / "evals" / "roto.eval.yaml").write_text("kind: Eval\n")
    assert cli.main([str(d)]) == 2


def test_sin_evals_sale_2(tmp_path):
    d = tmp_path / "vacio"
    d.mkdir()
    assert cli.main([str(d)]) == 2


def test_archivo_explicito(tmp_path, modelo_ok):
    d = _config(tmp_path)
    assert cli.main([str(d), str(d / "evals" / "e.eval.yaml")]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/evals/test_cli.py -q`
Expected: FAIL, porque `astromesh.evals.__main__` no existe.

- [ ] **Step 3: Write the implementation**

`astromesh/evals/__main__.py`:

```python
"""`astromesh-eval <config_dir> [archivo.eval.yaml ...] [--out reporte.json]`.

Exit: 0 si todos los evals cumplen sus umbrales, 1 si alguno no, 2 por error de carga
(en ese caso no corre ningún caso).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from astromesh.evals import fixtures
from astromesh.evals.formato import Eval, EvalError, cargar_eval
from astromesh.evals.runner import correr_eval


def _error(msg: str) -> int:
    print(f"astromesh-eval: {msg}", file=sys.stderr)
    return 2


def _tabla(ev: dict) -> None:
    print(f"\n{ev['name']} → {ev['agent']}")
    for c in ev["cases"]:
        tokens = c["tokens_in"] + c["tokens_out"]
        print(
            f"  {c['status']:<5} {c['id']:<24} {tokens:>7} tok  "
            f"${c['cost']:.4f}  {c['latency_ms']:>8.0f} ms"
        )
        for m in c["motivos"]:
            print(f"        · {m}")
    estado = "OK" if ev["passed"] else "BAJO UMBRAL"
    print(
        f"  pass_rate {ev['pass_rate']:.2f} · {ev['avg_tokens']:.0f} tok/caso · "
        f"${ev['total_cost']:.4f} · {estado}"
    )


async def correr(config_dir: str, evals: list[Eval], out: str | None) -> int:
    from astromesh.runtime.engine import AgentRuntime, build_candidate_provider

    runtime = AgentRuntime(config_dir=config_dir)
    await runtime.bootstrap()
    jueces = {}
    for ev in evals:
        if ev.agent not in runtime._agents:
            motivo = runtime._agent_errors.get(ev.agent, "no está en el árbol de config")
            return _error(f"{ev.path}: agente {ev.agent!r} no disponible: {motivo}")
        if ev.judge_model is not None:
            juez = build_candidate_provider(ev.judge_model)
            if juez is None:
                return _error(f"{ev.path}: judge.model no construye un provider")
            jueces[ev.path] = juez
    fixtures.preparar(runtime)
    run_id = uuid.uuid4().hex[:8]
    resultados = [await correr_eval(runtime, ev, run_id, jueces.get(ev.path)) for ev in evals]
    for r in resultados:
        _tabla(r)
    if out:
        Path(out).write_text(
            json.dumps({"run_id": run_id, "evals": resultados}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if all(r["passed"] for r in resultados) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="astromesh-eval", description="Corre evals de agentes.")
    p.add_argument("config_dir")
    p.add_argument("archivos", nargs="*", help="por defecto, <config_dir>/evals/*.eval.yaml")
    p.add_argument("--out", help="escribe el reporte JSON acá")
    args = p.parse_args(argv)
    archivos = args.archivos or sorted(Path(args.config_dir, "evals").glob("*.eval.yaml"))
    if not archivos:
        return _error(f"no hay evals en {Path(args.config_dir, 'evals')}")
    try:
        evals = [cargar_eval(a) for a in archivos]
    except EvalError as exc:
        return _error(str(exc))
    return asyncio.run(correr(args.config_dir, evals, args.out))


if __name__ == "__main__":
    sys.exit(main())
```

`pyproject.toml`: agregá esta sección después del bloque `[project.optional-dependencies]` (buscalo con `grep -n "^\[" pyproject.toml`):

```toml
[project.scripts]
astromesh-eval = "astromesh.evals.__main__:main"
```

Después corré `uv lock` en la raíz y commiteá `uv.lock` si cambió (`git diff --stat uv.lock`).

`CHANGELOG.md`: bajo `## [Unreleased]`, en una subsección `### Added` (creala arriba de `### Fixed` si no existe):

```markdown
### Added

- Evals de agentes: formato `kind: Eval` (`*.eval.yaml`, schema en
  `vscode-extension/schemas/eval.schema.json`) y el runner `astromesh-eval <config_dir>`.
  Casos de uno o más turnos con asserts (`contains`, `not_contains`, `regex`, `equals`,
  `tool_called`, `tool_not_called`) y una rúbrica opcional que califica un juez LLM. Las
  tools pueden llevar fixtures por caso (`tools_default: block` bloquea las demás) y la
  memoria conversacional corre aislada, sin tocar Redis. Reporta pass rate, tokens, caché,
  costo y latencia; sale con 1 bajo `thresholds` y con 2 por error de carga.
```

`docs/CONFIGURATION_GUIDE.md`: sección nueva al final.

````markdown
## Evals de agentes

Un eval es un `*.eval.yaml` en `<config_dir>/evals/` que corre casos contra un agente del
mismo árbol y falla bajo un umbral. Sirve como gate antes de cambiar un prompt, un modelo
o el presupuesto de contexto.

```yaml
apiVersion: astromesh/v1
kind: Eval
metadata:
  name: lucia-basico
spec:
  agent: lucia
  judge:                       # opcional; sólo para casos con rubric
    model: {provider: openai_compat, model: kimi-k2, endpoint: "https://api.moonshot.ai/v1", api_key_env: MOONSHOT_API_KEY}
    pass_score: 0.7
  tools_default: real          # real | block
  thresholds:
    pass_rate: 0.9
    max_avg_tokens: 6000       # opcional
  cases:
    - id: stock-simple
      turns: ["¿cuánto stock hay de X?"]
      tools: {consultar_stock: {sku: X, stock: 12}}
      expect:
        - contains: "12"
        - tool_called: consultar_stock
      rubric: "Responde con la cantidad y no inventa precios."
  cases_file: lucia.cases.jsonl  # opcional, un caso por línea
```

- `expect` se evalúa sobre la respuesta del último turno. `tool_called` y
  `tool_not_called` miran todas las llamadas del caso.
- Una tool con fixture no se ejecuta y devuelve ese valor; si el valor no es un mapa, llega
  como `{"result": valor}`. El resultado pasa igual por el tope `max_result_tokens`, y el
  gate de confirmación sigue aplicando.
- Los turnos de un caso comparten sesión, y la memoria conversacional corre en memoria.
- Correr: `uv run astromesh-eval config/ --out reporte.json`. Sale con `0` si todo pasa,
  `1` si algún eval queda bajo umbral y `2` por error de carga.
````

- [ ] **Step 4: Run tests to verify they pass, plus the whole suite**

Run: `uv run pytest tests/evals -q && uv run pytest -q`
Expected: PASS, con el total previo (2112 passed) más los tests nuevos.

Run: `uv run astromesh-eval --help`
Expected: imprime el uso, lo que prueba que el entry point quedó instalado (`uv sync` lo reinstala si hace falta).

Run: `uv run python -c "import astromesh.api.main, sys; assert not any(m.startswith('astromesh.evals') for m in sys.modules)"`
Expected: sin salida (`api.main` no importa `astromesh.evals`).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check astromesh/ tests/ && uv run ruff format --check astromesh/ tests/
git add astromesh/evals/__main__.py tests/evals/test_cli.py pyproject.toml uv.lock CHANGELOG.md docs/CONFIGURATION_GUIDE.md
git commit -m "feat(evals): CLI astromesh-eval, entry point y guía"
```

---

## Fuera de este plan

- **Página del docs-site** (`docs-site/src/content/docs/advanced/evals.md`): se escribe al hacer el release que publica el feature, no antes.
- **Concurrencia, repeticiones y A/B:** los suma el subproyecto DSPy.
