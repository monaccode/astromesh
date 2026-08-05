"""Los ejemplos versionados tienen que cargar y compilar de verdad."""

from pathlib import Path

import yaml

from astromesh.chain.compiler import compile_chain
from astromesh.chain.output import normalize_output_schema
from astromesh.workflow.loader import WorkflowLoader

RAIZ = Path(__file__).resolve().parents[1]


def _cargar_agentes():
    configs = {}
    for f in (RAIZ / "config" / "agents").glob("*.agent.yaml"):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        configs[raw["metadata"]["name"]] = raw
    return configs


def test_el_workflow_de_ejemplo_carga():
    ruta = RAIZ / "config" / "workflows" / "example.workflow.yaml"
    wf = WorkflowLoader(str(ruta.parent)).load_file(ruta)
    assert wf.name == "lead-qualification"


def test_todas_las_cadenas_de_config_compilan():
    """Si un ejemplo tiene un ciclo o apunta a un agente que no existe, acá se ve."""
    configs = _cargar_agentes()
    for nombre in configs:
        compile_chain(nombre, configs)  # no debe levantar


def test_sales_qualifier_declara_score_en_su_output_schema():
    configs = _cargar_agentes()
    schema = normalize_output_schema(configs["sales-qualifier"]["spec"].get("output_schema"))
    assert schema is not None, "el ejemplo de la doc depende de que declare output_schema"
    assert "score" in schema["properties"]


def test_el_when_del_workflow_de_ejemplo_referencia_un_campo_declarado():
    """El `when` versionado apuntaba a output.data.score sin que `data` existiera:
    con _SilentUndefined rendía vacío y caía al default en silencio."""
    ruta = RAIZ / "config" / "workflows" / "example.workflow.yaml"
    wf = WorkflowLoader(str(ruta.parent)).load_file(ruta)
    configs = _cargar_agentes()
    schema = normalize_output_schema(configs["sales-qualifier"]["spec"].get("output_schema"))

    condiciones = [
        b.get("when", "") for s in wf.steps if s.switch for b in s.switch if b.get("when")
    ]
    assert condiciones, "el ejemplo tenía un switch condicional"
    for cond in condiciones:
        if "output.data." in cond:
            campo = cond.split("output.data.")[1].split()[0].strip(" }")
            assert campo in schema["properties"], (
                f"el `when` referencia '{campo}', que sales-qualifier no declara"
            )


def test_los_agentes_referenciados_por_el_workflow_de_ejemplo_existen():
    """El workflow de ejemplo referenciaba agentes que no estaban versionados."""
    ruta = RAIZ / "config" / "workflows" / "example.workflow.yaml"
    wf = WorkflowLoader(str(ruta.parent)).load_file(ruta)
    configs = _cargar_agentes()

    faltantes = [s.agent for s in wf.steps if s.agent and s.agent not in configs]
    assert not faltantes, f"el workflow de ejemplo referencia agentes inexistentes: {faltantes}"
