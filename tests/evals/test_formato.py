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
    assert ev.name == "lucia-basico"
    assert ev.agent == "lucia"
    assert [c.id for c in ev.casos] == ["c1", "c2"]
    assert ev.casos[1].turns == ["a", "b"]
    assert ev.casos[1].rubric == "bien"
    assert ev.tools_default == "block"
    assert ev.max_avg_tokens == 6000
    assert ev.judge_model == {"provider": "ollama", "model": "llama3"}
    assert ev.judge_pass_score == 0.7
    assert ev.casos[0].context == {}
    assert ev.casos[0].tools == {}


@pytest.mark.parametrize(
    ("mutar", "fragmento"),
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


def test_id_con_salto_de_linea_final_se_rechaza(tmp_path):
    doc = _doc(cases=[{"id": "abc\n", "turns": ["a"], "expect": [{"contains": "a"}]}])
    with pytest.raises(EvalError):
        cargar_eval(_escribir(tmp_path, doc))


def test_clave_desconocida_en_la_raiz_se_rechaza(tmp_path):
    doc = _doc()
    doc["extra"] = 1
    with pytest.raises(EvalError):
        cargar_eval(_escribir(tmp_path, doc))
