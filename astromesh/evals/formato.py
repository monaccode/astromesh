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
_ID = re.compile(r"[a-z0-9_-]{1,64}")
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
    if not isinstance(cid, str) or not _ID.fullmatch(cid):
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
    try:
        texto = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise EvalError(f"{donde}: no se pudo leer cases_file {str(path)!r}: {exc}") from exc
    crudos = []
    for n, linea in enumerate(texto.splitlines(), start=1):
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
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise EvalError(f"{donde}: no se pudo leer: {exc}") from exc
    if not isinstance(doc, dict):
        raise EvalError(f"{donde}: el documento tiene que ser un mapa")
    if doc.get("apiVersion") != "astromesh/v1":
        raise EvalError(f"{donde}: apiVersion tiene que ser astromesh/v1")
    if doc.get("kind") != "Eval":
        raise EvalError(f"{donde}: kind tiene que ser Eval")
    _sobrantes(doc, {"apiVersion", "kind", "metadata", "spec"}, donde)
    metadata = doc.get("metadata")
    nombre = metadata.get("name") if isinstance(metadata, dict) else None
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
