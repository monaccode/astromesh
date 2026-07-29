"""compile_chain: spec.chain -> WorkflowSpec ejecutable por el motor."""

import pytest

from astromesh.chain.compiler import chain_graph, chain_workflow_name, compile_chain
from astromesh.workflow.models import StepType


def _agente(nombre, chain=None, output_schema=None):
    spec = {"identity": {"description": nombre}}
    if chain:
        spec["chain"] = chain
    if output_schema:
        spec["output_schema"] = output_schema
    return {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": nombre},
        "spec": spec,
    }


def _configs(*agentes):
    return {a["metadata"]["name"]: a for a in agentes}


def test_nombre_reservado():
    assert chain_workflow_name("a") == "__chain__a"


def test_el_paso_cero_es_el_agente_mismo():
    configs = _configs(_agente("a", {"on_complete": [{"agent": "b"}]}), _agente("b"))
    wf = compile_chain("a", configs)

    assert wf.name == "__chain__a"
    assert wf.steps[0].agent == "a"
    assert wf.steps[0].step_type == StepType.AGENT
    assert wf.steps[0].input_template == "{{ trigger.query }}"
    assert wf.steps[0].when is None, "el agente invocado siempre corre"


def test_un_paso_por_eslabon_con_su_guarda():
    configs = _configs(
        _agente(
            "a",
            {
                "on_complete": [
                    {"agent": "b", "when": "{{ output.data.score > 7 }}"},
                    {"agent": "c"},
                ]
            },
        ),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert [s.agent for s in wf.steps] == ["a", "b", "c"]
    assert wf.steps[1].when == "{{ steps.a.output.data.score > 7 }}"
    assert wf.steps[2].when is None, "un eslabón sin `when` dispara siempre"


def test_las_guardas_son_estrictas():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b", "when": "{{ x }}"}]}), _agente("b")
    )
    wf = compile_chain("a", configs)
    assert wf.steps[1].strict_conditions is True


def test_output_apunta_al_agente_anterior():
    """`output` en un eslabón de A se reescribe a `steps.<A>.output`."""
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b", "when": "{{ output.data.score > 7 }}"}]}),
        _agente("b"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].when == "{{ steps.a.output.data.score > 7 }}"
    assert wf.steps[1].input_template == "{{ steps.a.output.answer }}"


def test_regla_default_niega_las_guardas_previas():
    configs = _configs(
        _agente(
            "a",
            {
                "on_complete": [
                    {"agent": "b", "when": "{{ output.data.score > 7 }}"},
                    {"agent": "c"},
                    {"agent": "d", "default": True},
                ]
            },
        ),
        _agente("b"),
        _agente("c"),
        _agente("d"),
    )
    wf = compile_chain("a", configs)

    paso_default = wf.steps[3]
    assert paso_default.agent == "d"
    # sólo `b` tiene guarda; `c` no cuenta como match
    assert paso_default.when == "{{ not (when['a__b']) }}"
    assert paso_default.strict_conditions is True


def test_default_sin_guardas_previas_dispara_siempre():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}, {"agent": "c", "default": True}]}),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)
    assert wf.steps[2].when is None


def test_modo_paralelo_produce_un_paso_parallel():
    configs = _configs(
        _agente("a", {"mode": "parallel", "on_complete": [{"agent": "b"}, {"agent": "c"}]}),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].step_type == StepType.PARALLEL
    assert [s.agent for s in wf.steps[1].parallel] == ["b", "c"]


def test_paralelo_deja_el_default_como_paso_posterior():
    """El default necesita las guardas ya evaluadas, así que va después del fanout."""
    configs = _configs(
        _agente(
            "a",
            {
                "mode": "parallel",
                "on_complete": [
                    {"agent": "b", "when": "{{ output.data.score > 7 }}"},
                    {"agent": "c", "default": True},
                ],
            },
        ),
        _agente("b"),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].step_type == StepType.PARALLEL
    assert wf.steps[2].agent == "c"
    assert wf.steps[2].when == "{{ not (when['a__b']) }}"


def test_campos_de_fallo_se_propagan():
    configs = _configs(
        _agente(
            "a",
            {
                "on_complete": [
                    {
                        "agent": "b",
                        "retry": {"max_attempts": 3, "backoff": "exponential"},
                        "timeout_seconds": 30,
                        "on_error": "continue",
                    }
                ]
            },
        ),
        _agente("b"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[1].retry.max_attempts == 3
    assert wf.steps[1].retry.backoff == "exponential"
    assert wf.steps[1].timeout_seconds == 30
    assert wf.steps[1].on_error == "continue"


def test_expansion_recursiva():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "c"}]}),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert [s.agent for s in wf.steps] == ["a", "b", "c"]


def test_la_guarda_anidada_apunta_a_su_propio_padre():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "c", "when": "{{ output.data.ok }}"}]}),
        _agente("c"),
    )
    wf = compile_chain("a", configs)

    assert wf.steps[2].when == "{{ steps.b.output.data.ok }}"


def test_ciclo_da_error_nombrando_la_ruta():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "a"}]}),
    )
    with pytest.raises(ValueError, match="ciclo"):
        compile_chain("a", configs)

    with pytest.raises(ValueError, match="a -> b -> a"):
        compile_chain("a", configs)


def test_max_depth_excedido_da_error():
    configs = _configs(
        _agente("a", {"max_depth": 2, "on_complete": [{"agent": "b"}]}),
        _agente("b", {"on_complete": [{"agent": "c"}]}),
        _agente("c", {"on_complete": [{"agent": "d"}]}),
        _agente("d"),
    )
    with pytest.raises(ValueError, match="max_depth"):
        compile_chain("a", configs)


def test_agente_inexistente_da_error_nombrando_al_referente():
    configs = _configs(_agente("a", {"on_complete": [{"agent": "fantasma"}]}))
    with pytest.raises(ValueError, match="fantasma"):
        compile_chain("a", configs)
    with pytest.raises(ValueError, match="'a'"):
        compile_chain("a", configs)


def test_agente_sin_cadena_no_compila():
    configs = _configs(_agente("a"))
    assert compile_chain("a", configs) is None


def test_los_nombres_de_paso_son_unicos_por_padre():
    """El mismo agente bajo dos padres no puede pisarse."""
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b"}, {"agent": "c"}]}),
        _agente("b", {"on_complete": [{"agent": "log"}]}),
        _agente("c", {"on_complete": [{"agent": "log"}]}),
        _agente("log"),
    )
    wf = compile_chain("a", configs)

    nombres = [s.name for s in wf.steps]
    assert len(nombres) == len(set(nombres)), f"nombres duplicados: {nombres}"
    assert "b__log" in nombres
    assert "c__log" in nombres


def test_grafo_expandido():
    configs = _configs(
        _agente("a", {"on_complete": [{"agent": "b", "when": "{{ output.data.score > 7 }}"}]}),
        _agente("b", {"on_complete": [{"agent": "c"}]}),
        _agente("c"),
    )
    grafo = chain_graph("a", configs)

    assert grafo["agent"] == "a"
    assert grafo["mode"] == "sequential"
    assert grafo["max_depth"] == 5
    assert grafo["links"][0] == {
        "agent": "b",
        "depth": 1,
        "via": None,
        "when": "{{ output.data.score > 7 }}",
        "default": False,
    }
    assert grafo["links"][1] == {
        "agent": "c",
        "depth": 2,
        "via": "b",
        "when": None,
        "default": False,
    }


def test_grafo_none_si_no_hay_cadena():
    assert chain_graph("a", _configs(_agente("a"))) is None
